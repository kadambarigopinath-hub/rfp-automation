"""
Implements the staged duplicate-check pipeline (see ARCHITECTURE.md §4a and
KB_PRODUCT_REQUIREMENTS.md KB-19 to KB-19a):

  Stage 1: SHA-256 exact match (free, always runs)
  Stage 2: SimHash near-duplicate match on extracted text (free, always runs)
  Stage 3: Semantic embedding comparison (only if Stage 1/2 inconclusive, and only
           if EMBEDDING_PROVIDER=local is configured and the optional ML deps are installed)

Returns one of:
  {"match_type": "exact", "document": <Document>, "version": <DocumentVersion>}
  {"match_type": "near",  "document": <Document>, "version": <DocumentVersion>}
  {"match_type": "none"}

The caller decides what to DO with the result (prompt user to overwrite / confirm new
version / proceed) — this module only detects, it never rejects or accepts on its own.
"""

import hashlib
from sqlalchemy.orm import Session

from app.models.models import Document, DocumentVersion
from app.core.config import settings

try:
    from datasketch import MinHash
    HAS_DATASKETCH = True
except ImportError:
    HAS_DATASKETCH = False


def sha256_of_bytes(file_bytes: bytes) -> str:
    return hashlib.sha256(file_bytes).hexdigest()


def compute_simhash(text: str):
    """Returns a 64-bit-ish integer fingerprint tolerant of small text edits.
    Falls back to None if datasketch isn't installed — Stage 2 is then skipped
    gracefully, degrading to Stage 1 + (if available) Stage 3 only."""
    if not HAS_DATASKETCH or not text.strip():
        return None
    m = MinHash(num_perm=64)
    for word in text.split():
        m.update(word.encode("utf8"))
    return int.from_bytes(hashlib.sha1(m.digest().tobytes()).digest()[:8], "big")


def hamming_distance(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def check_duplicate(db: Session, folder_id: str, file_bytes: bytes, extracted_text: str) -> dict:
    file_hash = sha256_of_bytes(file_bytes)

    # --- Stage 1: exact match ---
    exact = (
        db.query(DocumentVersion)
        .join(Document, Document.id == DocumentVersion.document_id)
        .filter(Document.folder_id == folder_id, Document.status == "active",
                DocumentVersion.content_sha256 == file_hash)
        .first()
    )
    if exact:
        doc = db.query(Document).get(exact.document_id)
        return {"match_type": "exact", "document": doc, "version": exact, "new_hash": file_hash,
                "new_simhash": None}

    # --- Stage 2: near-duplicate (simhash) ---
    new_simhash = compute_simhash(extracted_text)
    if new_simhash is not None:
        candidates = (
            db.query(DocumentVersion)
            .join(Document, Document.id == DocumentVersion.document_id)
            .filter(Document.folder_id == folder_id, Document.status == "active",
                    DocumentVersion.content_simhash.isnot(None))
            .all()
        )
        for candidate in candidates:
            if hamming_distance(new_simhash, candidate.content_simhash) <= settings.near_duplicate_simhash_threshold:
                doc = db.query(Document).get(candidate.document_id)
                return {"match_type": "near", "document": doc, "version": candidate,
                        "new_hash": file_hash, "new_simhash": new_simhash}

    # --- Stage 3: semantic embedding compare (optional, only if inconclusive above) ---
    try:
        from app.services.embeddings import embed_text, cosine_similarity
        if settings.embedding_provider == "local":
            new_embedding = embed_text(extracted_text[:3000])
            if new_embedding is not None:
                from app.models.models import DocumentCentroid
                centroids = (
                    db.query(DocumentCentroid)
                    .join(DocumentVersion, DocumentVersion.id == DocumentCentroid.document_version_id)
                    .join(Document, Document.id == DocumentVersion.document_id)
                    .filter(Document.folder_id == folder_id, Document.status == "active")
                    .all()
                )
                for c in centroids:
                    sim = cosine_similarity(new_embedding, c.centroid)
                    if sim >= settings.near_duplicate_cosine_threshold:
                        version = db.query(DocumentVersion).get(c.document_version_id)
                        doc = db.query(Document).get(version.document_id)
                        return {"match_type": "near", "document": doc, "version": version,
                                "new_hash": file_hash, "new_simhash": new_simhash}
    except ImportError:
        pass  # embeddings module's optional ML deps not installed — skip Stage 3 silently

    return {"match_type": "none", "new_hash": file_hash, "new_simhash": new_simhash}
