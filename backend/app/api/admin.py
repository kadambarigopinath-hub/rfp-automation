"""Superadmin-only: tag taxonomy config (KB-13/13a) and audit log viewing (KB-22)."""

import uuid
from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.api.deps import get_current_user
from app.models.models import User, Folder, TagTaxonomy, AuditLog, ChangeHistory

router = APIRouter()
templates = Jinja2Templates(directory="templates")

PERSONAS = ["legal", "infosec", "infrastructure", "product", "business", "engineering"]


def require_superadmin(user: User):
    if user.role.name != "superadmin":
        raise HTTPException(status_code=403, detail="Superadmin only")


@router.get("/admin/taxonomy", response_class=HTMLResponse)
def taxonomy_list(request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    require_superadmin(user)
    folders = db.query(Folder).filter(Folder.folder_type == "kb_persona").all()
    taxonomy_by_folder = {}
    for f in folders:
        taxonomy_by_folder[f.name] = db.query(TagTaxonomy).filter(TagTaxonomy.folder_id == f.id).all()
    return templates.TemplateResponse("admin_taxonomy.html", {
        "request": request, "folders": folders, "taxonomy_by_folder": taxonomy_by_folder,
    })


@router.post("/admin/taxonomy/add")
async def taxonomy_add(request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    require_superadmin(user)
    form = await request.form()
    folder_name = form.get("folder_name")
    tag_key = form.get("tag_key")
    allowed_values_raw = form.get("allowed_values", "")
    required = form.get("required") == "on"

    folder = db.query(Folder).filter(Folder.name == folder_name, Folder.folder_type == "kb_persona").first()
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")

    allowed_values = [v.strip() for v in allowed_values_raw.split(",") if v.strip()] or None

    db.add(TagTaxonomy(id=str(uuid.uuid4()), folder_id=folder.id, tag_key=tag_key,
                        allowed_values=allowed_values, required=required))
    db.commit()
    return RedirectResponse(url="/admin/taxonomy", status_code=303)


@router.get("/admin/audit", response_class=HTMLResponse)
def audit_log_view(request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    require_superadmin(user)
    logs = db.query(AuditLog).order_by(AuditLog.created_at.desc()).limit(200).all()
    changes = db.query(ChangeHistory).order_by(ChangeHistory.changed_at.desc()).limit(200).all()
    return templates.TemplateResponse("admin_audit.html", {"request": request, "logs": logs, "changes": changes})
