"""Best-effort text extraction. No OCR — scanned/image-only PDFs won't extract cleanly
(flagged as a known gap in ARCHITECTURE.md, non-functional requirements)."""

import io


def extract_text(filename: str, file_bytes: bytes) -> str:
    lower = filename.lower()
    try:
        if lower.endswith(".txt") or lower.endswith(".md"):
            return file_bytes.decode("utf-8", errors="ignore")
        elif lower.endswith(".docx"):
            from docx import Document
            doc = Document(io.BytesIO(file_bytes))
            return "\n".join(p.text for p in doc.paragraphs)
        elif lower.endswith(".pdf"):
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(file_bytes))
            return "\n".join((page.extract_text() or "") for page in reader.pages)
        else:
            return ""
    except Exception as e:
        return f"[Could not extract text: {e}]"
