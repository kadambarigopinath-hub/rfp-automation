# Knowledge Base Module — Full Production Backend

Implements the Knowledge Base requirements from `KB_PRODUCT_REQUIREMENTS.md` on the full
production stack: FastAPI + Postgres (with pgvector) + S3-compatible storage (MinIO
locally) + Docker.

## What's implemented

- Persona folder isolation + RBAC (KB-01 to KB-08)
- No in-place editing — every update is a new immutable version (KB-09, KB-10, KB-12a)
- Full version history (KB-11, KB-12)
- Tag taxonomy per folder, including required-tag enforcement (KB-13, KB-13a, KB-13b)
- AI-suggested tags and filenames via Claude, editable before confirming (KB-14 to KB-18)
- Staged duplicate detection: exact hash match → near-duplicate (SimHash) → optional
  semantic (embedding) compare (KB-19 to KB-21)
- Exact-match and near-duplicate flows prompt the user rather than silently
  rejecting/accepting (KB-19a, KB-20, KB-21) — includes the "is this a new version of an
  existing document?" confirmation flow, which never touches the separate Product Version
  tag (KB-12a)
- Audit logging (KB-22) and universal field-level change history (KB-23)
- Vector embedding of accepted documents for RAG (KB-31 to KB-35) — feature-flagged,
  degrades gracefully if the optional ML dependencies aren't installed
- Superadmin tag taxonomy configuration and audit log viewer

## What's NOT yet implemented (known gaps for the next build phase)

- MFA, full JWT-based auth (currently: hashed passwords + signed session cookie)
- Malware/virus scanning on upload
- OCR for scanned PDFs
- RFP Agent module (separate scope, see ARCHITECTURE.md/SKILLS.md)
- The `Form()`-typed `/upload/confirm` route was replaced by `/upload/finalize`, which
  parses form data manually to support the dynamic per-folder tag fields — this is a
  reasonable pattern to keep, not a shortcut to fix later.

## Setup

### 1. Start the infrastructure (Postgres, MinIO)
From the **project root** (one level up from this `backend/` folder):
