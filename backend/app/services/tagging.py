"""
Handles KB-13 through KB-18: tag auto-suggestion, filename nomenclature suggestion,
and taxonomy validation (including required-tag enforcement, KB-13a/KB-13b).
"""

import json
import os
from anthropic import Anthropic

from app.core.config import settings

client = Anthropic(api_key=settings.anthropic_api_key)


def suggest_tags_and_doctype(extracted_text: str, taxonomy: list) -> dict:
    """taxonomy: list of {"tag_key": str, "allowed_values": list|None, "required": bool}
    Returns: {"doctype": str, "tags": {tag_key: value, ...}}"""
    taxonomy_desc = "\n".join(
        f"- {t['tag_key']}" + (f" (allowed values: {t['allowed_values']})" if t.get("allowed_values") else "") +
        (" [REQUIRED]" if t.get("required") else " [optional]")
        for t in taxonomy
    )
    system = (
        "You suggest metadata tags for a document being added to a knowledge base. "
        "Only use the tag keys provided — do not invent new ones. Respond ONLY with JSON: "
        '{"doctype": "...", "tags": {"tag_key": "value", ...}}. '
        "If you cannot confidently determine a value for a tag, omit it from the tags object "
        "rather than guessing."
    )
    user = f"Available tags for this folder:\n{taxonomy_desc}\n\nDocument content (excerpt):\n{extracted_text[:4000]}"
    resp = client.messages.create(
        model=settings.claude_model,
        max_tokens=500,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    raw = "".join(b.text for b in resp.content if b.type == "text")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        cleaned = raw.strip().strip("`").replace("json\n", "", 1)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            return {"doctype": "", "tags": {}}


def suggest_filename(doctype: str, tags: dict, version_number: int) -> str:
    """KB-17: {Doctype}_{ProductName}_v{Version}_{YYYYMMDD} — falls back gracefully
    if product_name isn't one of this folder's tags."""
    from datetime import date
    doctype_part = (doctype or "Document").replace(" ", "")
    product_part = tags.get("product_name", tags.get("Product Name", "General")).replace(" ", "")
    date_part = date.today().strftime("%Y%m%d")
    return f"{doctype_part}_{product_part}_v{version_number}_{date_part}"


def validate_tags_against_taxonomy(tags: dict, taxonomy: list) -> list:
    """Returns a list of validation error strings; empty list = valid.
    Enforces KB-16 (only defined keys/values allowed) and KB-13b (required tags present)."""
    errors = []
    taxonomy_by_key = {t["tag_key"]: t for t in taxonomy}

    for key, value in tags.items():
        if key not in taxonomy_by_key:
            errors.append(f"'{key}' is not a valid tag for this folder.")
            continue
        allowed = taxonomy_by_key[key].get("allowed_values")
        if allowed and value not in allowed:
            errors.append(f"'{value}' is not an allowed value for '{key}'. Allowed: {allowed}")

    for t in taxonomy:
        if t.get("required") and not tags.get(t["tag_key"]):
            errors.append(f"'{t['tag_key']}' is required and was not provided.")

    return errors
