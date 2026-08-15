"""
Local embedding model wrapper. Used for:
  1. Stage 3 of duplicate detection (dedup.py) — only reached if Stage 1/2 are inconclusive
  2. RAG indexing of accepted documents (index_document_version below)

Uses a self-hosted model (sentence-transformers) rather than a metered API by default,
per the cost discussion in ARCHITECTURE.md §4a — no per-call cost as document volume grows.

If sentence-transformers/torch aren't installed, every function here returns None/no-ops,
and callers (dedup.py, kb.py) are written to handle that gracefully — embedding is always
an enhancement, never a hard requirement for the KB to function.
"""

import numpy as np
from app.core.config import settings

_model = None


def _get_model():
    global _model
    if _model is not None:
        return _model
    try:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer(settings.local_embedding_model)
        return _model
    except ImportError:
        return None


def embed_text(text: str):
    """Returns a list[float] embedding, or None if the optional ML deps aren't installed
    or the provider is set to 'none'."""
    if settings.embedding_provider != "local" or not text.strip():
        return None
    model = _get_model()
    if model is None:
        return None
    vec = model.encode(text, normalize_embeddings=True)
    return vec.tolist()


def cosine_similarity(vec_a, vec_b) -> float:
    a = np.array(vec_a)
    b = np.array(vec_b)
    denom = (np.linalg.norm(a) * np.linalg.norm(b))
    if denom == 0:
        return 0.0
    return float(np.dot(a, b) / denom)


def chunk_text(text: str, chunk_size: int = 800, overlap: int = 100) -> list:
    """Simple fixed-size chunking with overlap. Fine for a first pass; a production
    build may want sentence/paragraph-aware chunking instead."""
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start = end - overlap
        if start < 0 or end >= len(text):
            break
    return [c for c in chunks if c.strip()]


def index_document_version(db, document_version_id: str, full_text: str):
    """Chunks + embeds an ACCEPTED document version for RAG (KB-31/KB-32), and stores
    a centroid (mean of chunk embeddings) for future Stage 3 dedup checks (KB-19a scope
    note: this only ever runs on accepted, non-duplicate content — see dedup.py)."""
    if settings.embedding_provider != "local":
        return
    model = _get_model()
    if model is None:
        return

    from app.models.models import DocumentEmbedding, DocumentCentroid

    chunks = chunk_text(full_text)
    if not chunks:
        return

    vectors = []
    for i, chunk in enumerate(chunks):
        vec = embed_text(chunk)
        if vec is None:
            continue
        vectors.append(vec)
        db.add(DocumentEmbedding(
            document_version_id=document_version_id,
            chunk_index=i,
            chunk_text=chunk,
            embedding=vec,
        ))

    if vectors:
        centroid = np.mean(np.array(vectors), axis=0).tolist()
        db.add(DocumentCentroid(document_version_id=document_version_id, centroid=centroid))

    db.commit()
