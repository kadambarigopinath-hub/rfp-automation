"""
Implements KB-01 through KB-22 and KB-31 through KB-35 (folders/RBAC, upload flow with
staged duplicate + version-confirm prompts, tagging, naming, version control, download,
delete, and RAG indexing on acceptance).
"""

import uuid
import secrets
from fastapi import APIRouter, Depends, Request, UploadFile, File, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
import io

from app.core.db import get_db
from app.core.config import settings
from app.api.deps import get_current_user
from app.models.models import Folder, Document, DocumentVersion, DocumentTag, TagTaxonomy, User
from app.services.extract import extract_text
from app.services.dedup import check_duplicate
from app.services.tagging import suggest_tags_and_doctype, suggest_filename, validate_tags_against_taxonomy
from app.services.audit import log_action, log_change
from app.services import embeddings
from app.storage import s3_client

router = APIRouter()
templates = Jinja2Templates(directory="templates")

PERSONAS = ["legal", "infosec", "infrastructure", "product", "business", "engineering"]

_staging_registry = {}


def get_folder_or_404(db: Session, folder_name: str) -> Folder:
    folder = db.query(Folder).filter(Folder.name == folder_name, Folder.folder_type == "kb_persona").first()
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    return folder


def check_folder_access(user: User, folder_name: str, write: bool = False):
    if user.role.name == "superadmin":
        return
    if user.role.name != folder_name:
        raise HTTPException(status_code=403, detail="You do not have access to this folder")


def get_taxonomy(db: Session, folder_id: str) -> list:
    rows = db.query(TagTaxonomy).filter(TagTaxonomy.folder_id == folder_id).all()
    return [{"tag_key": r.tag_key, "allowed_values": r.allowed_values, "required": r.required} for r in rows]


@router.get("/kb", response_class=HTMLResponse)
def kb_root(request: Request, user: User = Depends(get_current_user)):
    default_folder = user.role.name if user.role.name in PERSONAS else PERSONAS[0]
    return RedirectResponse(url=f"/kb/{default_folder}")


@router.get("/kb/{folder_name}", response_class=HTMLResponse)
def kb_folder_view(request: Request, folder_name: str, db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    check_folder_access(user, folder_name)
    folder = get_folder_or_404(db, folder_name)
    docs = (
        db.query(Document)
        .filter(Document.folder_id == folder.id, Document.status == "active")
        .order_by(Document.created_at.desc())
        .all()
    )
    doc_rows = []
    for d in docs:
        version = db.query(DocumentVersion).get(d.current_version_id) if d.current_version_id else None
        tags = {}
        if version:
            tags = {t.tag_key: t.tag_value for t in db.query(DocumentTag).filter(DocumentTag.document_version_id == version.id)}
        doc_rows.append({"doc": d, "version": version, "tags": tags})

    can_write = (user.role.name == folder_name) or (user.role.name == "superadmin")
    return templates.TemplateResponse("kb_folder.html", {
        "request": request, "folder_name": folder_name, "docs": doc_rows,
        "can_write": can_write, "personas": PERSONAS, "user": user,
    })


@router.get("/kb/{folder_name}/upload", response_class=HTMLResponse)
def upload_form(request: Request, folder_name: str, user: User = Depends(get_current_user)):
    check_folder_access(user, folder_name, write=True)
    return templates.TemplateResponse("upload.html", {"request": request, "folder_name": folder_name})


@router.post("/kb/{folder_name}/upload/check", response_class=HTMLResponse)
async def upload_check(request: Request, folder_name: str, file: UploadFile = File(...),
                        db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Stage 1: run duplicate detection + AI tag/name suggestion, stage the file,
    and render the confirmation screen — nothing is saved to the KB yet."""
    check_folder_access(user, folder_name, write=True)
    folder = get_folder_or_404(db, folder_name)

    file_bytes = await file.read()
    extracted = extract_text(file.filename, file_bytes)

    dup_result = check_duplicate(db, folder.id, file_bytes, extracted)
    taxonomy = get_taxonomy(db, folder.id)
    suggestion = suggest_tags_and_doctype(extracted, taxonomy)

    if dup_result["match_type"] in ("exact", "near"):
        matched_doc = dup_result["document"]
        next_version = db.query(DocumentVersion).filter(
            DocumentVersion.document_id == matched_doc.id
        ).count() + 1
    else:
        matched_doc = None
        next_version = 1

    suggested_name = suggest_filename(suggestion.get("doctype", ""), suggestion.get("tags", {}), next_version)

    token = secrets.token_urlsafe(16)
    staging_key = f"{folder_name}/{token}_{file.filename}"
    s3_client.put_object(settings.s3_bucket_staging, staging_key, file_bytes)
    _staging_registry[token] = {
        "folder_id": folder.id, "folder_name": folder_name, "filename": file.filename,
        "staging_key": staging_key, "content_hash": dup_result["new_hash"],
        "content_simhash": dup_result.get("new_simhash"),
        "matched_document_id": matched_doc.id if matched_doc else None,
        "matched_document_name": matched_doc.display_name if matched_doc else None,
        "next_version": next_version,
    }

    return templates.TemplateResponse("upload_confirm.html", {
        "request": request, "folder_name": folder_name, "token": token,
        "match_type": dup_result["match_type"],
        "matched_document_name": matched_doc.display_name if matched_doc else None,
        "matched_version": next_version - 1 if matched_doc else None,
        "suggested_name": suggested_name, "suggested_doctype": suggestion.get("doctype", ""),
        "suggested_tags": suggestion.get("tags", {}), "taxonomy": taxonomy,
    })


@router.post("/kb/{folder_name}/upload/finalize")
async def upload_finalize(request: Request, folder_name: str, db: Session = Depends(get_db),
                           user: User = Depends(get_current_user)):
    """
    Actual finalize handler (dynamic tag fields require raw form parsing, which FastAPI's
    typed Form() params don't support directly for arbitrary keys). The upload_confirm.html
    template posts here instead of /upload/confirm.
    """
    check_folder_access(user, folder_name, write=True)
    folder = get_folder_or_404(db, folder_name)
    form = await request.form()

    token = form.get("token")
    decision = form.get("decision")
    display_name = form.get("display_name")
    doctype = form.get("doctype")

    staged = _staging_registry.get(token)
    if not staged:
        raise HTTPException(status_code=400, detail="Upload session expired or invalid. Please re-upload.")

    if decision == "cancel":
        s3_client.delete_object(settings.s3_bucket_staging, staged["staging_key"])
        del _staging_registry[token]
        return RedirectResponse(url=f"/kb/{folder_name}", status_code=303)

    taxonomy = get_taxonomy(db, folder.id)
    tags = {}
    for t in taxonomy:
        field_name = f"tag_{t['tag_key']}"
        if field_name in form and form[field_name]:
            tags[t["tag_key"]] = form[field_name]

    errors = validate_tags_against_taxonomy(tags, taxonomy)
    if errors:
        raise HTTPException(status_code=400, detail="; ".join(errors))

    file_bytes = s3_client.get_object(settings.s3_bucket_staging, staged["staging_key"])

    if decision in ("link_as_new_version", "save_anyway_same_content") and staged["matched_document_id"]:
        document = db.query(Document).get(staged["matched_document_id"])
        version_number = staged["next_version"]
    else:
        document = Document(id=str(uuid.uuid4()), folder_id=folder.id, display_name=display_name,
                             doctype=doctype, created_by=user.id, status="active")
        db.add(document)
        db.flush()
        version_number = 1

    permanent_key = f"{folder_name}/{document.id}/v{version_number}_{staged['filename']}"
    s3_client.copy_object(settings.s3_bucket_staging, staged["staging_key"], settings.s3_bucket_kb_permanent, permanent_key)
    s3_client.delete_object(settings.s3_bucket_staging, staged["staging_key"])

    version = DocumentVersion(
        id=str(uuid.uuid4()), document_id=document.id, version_number=version_number,
        storage_key=permanent_key, file_type=staged["filename"].split(".")[-1],
        file_size_bytes=len(file_bytes), content_sha256=staged["content_hash"],
        content_simhash=staged["content_simhash"], uploaded_by=user.id,
    )
    db.add(version)
    db.flush()

    for key, value in tags.items():
        db.add(DocumentTag(document_version_id=version.id, tag_key=key, tag_value=value))

    document.display_name = display_name
    document.doctype = doctype
    document.current_version_id = version.id
    db.commit()

    log_action(db, user.id, "document.upload", "document", document.id,
               {"version": version_number, "decision": decision})
    log_change(db, "document", document.id, "current_version_id", None, version.id, user.id)

    extracted = extract_text(staged["filename"], file_bytes)
    embeddings.index_document_version(db, version.id, extracted)

    del _staging_registry[token]
    return RedirectResponse(url=f"/kb/{folder_name}", status_code=303)


@router.get("/kb/{folder_name}/document/{document_id}/download")
def download_document(folder_name: str, document_id: str, version: int = None,
                       db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    check_folder_access(user, folder_name)
    document = db.query(Document).get(document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    if version:
        doc_version = db.query(DocumentVersion).filter(
            DocumentVersion.document_id == document_id, DocumentVersion.version_number == version
        ).first()
    else:
        doc_version = db.query(DocumentVersion).get(document.current_version_id)

    if not doc_version:
        raise HTTPException(status_code=404, detail="Version not found")

    file_bytes = s3_client.get_object(settings.s3_bucket_kb_permanent, doc_version.storage_key)
    log_action(db, user.id, "document.download", "document", document_id, {"version": doc_version.version_number})

    filename = doc_version.storage_key.split("/")[-1]
    return StreamingResponse(io.BytesIO(file_bytes), media_type="application/octet-stream",
                              headers={"Content-Disposition": f"attachment; filename={filename}"})


@router.get("/kb/{folder_name}/document/{document_id}/versions", response_class=HTMLResponse)
def version_history(request: Request, folder_name: str, document_id: str,
                     db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    check_folder_access(user, folder_name)
    document = db.query(Document).get(document_id)
    versions = db.query(DocumentVersion).filter(
        DocumentVersion.document_id == document_id
    ).order_by(DocumentVersion.version_number.desc()).all()
    return templates.TemplateResponse("version_history.html", {
        "request": request, "document": document, "versions": versions, "folder_name": folder_name,
    })


@router.post("/kb/{folder_name}/document/{document_id}/delete")
def delete_document(folder_name: str, document_id: str, db: Session = Depends(get_db),
                     user: User = Depends(get_current_user)):
    check_folder_access(user, folder_name, write=True)
    document = db.query(Document).get(document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    old_status = document.status
    document.status = "deleted"
    db.commit()
    log_action(db, user.id, "document.delete", "document", document_id)
    log_change(db, "document", document_id, "status", old_status, "deleted", user.id)
    return RedirectResponse(url=f"/kb/{folder_name}", status_code=303)
