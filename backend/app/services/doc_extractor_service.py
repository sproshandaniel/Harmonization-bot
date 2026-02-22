import io
import re
import zipfile
import xml.etree.ElementTree as ET

import fitz
from fastapi import UploadFile

from app.services.extractor_service import extract_rules_multi_pipeline


def _extract_text_from_docx_bytes(content: bytes) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            xml_text = archive.read("word/document.xml")
    except Exception:
        return ""

    try:
        root = ET.fromstring(xml_text)
    except Exception:
        return ""

    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    lines: list[str] = []
    for para in root.findall(".//w:p", ns):
        parts = [node.text for node in para.findall(".//w:t", ns) if node.text]
        text = "".join(parts).strip()
        if text:
            lines.append(text)
    return "\n".join(lines)


def _extract_text_from_plain_bytes(content: bytes) -> str:
    for encoding in ("utf-8", "utf-16", "latin-1"):
        try:
            return content.decode(encoding, errors="ignore")
        except Exception:
            continue
    return ""


def _normalize_text(text: str) -> str:
    cleaned_lines = [line.strip() for line in str(text or "").splitlines() if line.strip()]
    cleaned = "\n".join(cleaned_lines)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _chunk_text(text: str, max_chars: int = 7000, overlap_chars: int = 700) -> list[str]:
    source = str(text or "").strip()
    if not source:
        return []
    if len(source) <= max_chars:
        return [source]

    chunks: list[str] = []
    start = 0
    length = len(source)
    while start < length:
        end = min(start + max_chars, length)
        if end < length:
            boundary = source.rfind("\n", start, end)
            if boundary > start + max_chars // 2:
                end = boundary
        chunk = source[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= length:
            break
        start = max(0, end - overlap_chars)
    return chunks


def _dedupe_rules(rules: list[dict]) -> list[dict]:
    seen_yaml: set[str] = set()
    deduped: list[dict] = []
    for rule in rules:
        yaml_text = str(rule.get("yaml") or "").strip()
        if not yaml_text or yaml_text in seen_yaml:
            continue
        seen_yaml.add(yaml_text)
        deduped.append(rule)
    return deduped

async def process_document(
    file: UploadFile,
    rule_type: str = "code",
    rule_types: list[str] | None = None,
    max_rules: int = 5,
    wizard_name: str | None = None,
    wizard_description: str | None = None,
    wizard_step_title: str | None = None,
    wizard_step_description: str | None = None,
    wizard_step_snippet: str | None = None,
    wizard_step_no: int | None = None,
    wizard_total_steps: int | None = None,
    template_use_ai: bool = False,
    created_by: str = "anonymous",
):
    filename = str(file.filename or "").lower()
    content = await file.read()

    # Extract text depending on file type.
    if filename.endswith(".pdf"):
        text = extract_text_from_pdf(io.BytesIO(content))
    elif filename.endswith(".docx"):
        text = _extract_text_from_docx_bytes(content)
    else:
        text = _extract_text_from_plain_bytes(content)

    cleaned = _normalize_text(text)
    if not cleaned:
        return []

    safe_max_rules = max(1, min(int(max_rules or 1), 10))
    selected_types = rule_types or [rule_type]
    chunks = _chunk_text(cleaned, max_chars=7000, overlap_chars=700)
    if not chunks:
        chunks = [cleaned[:12000]]

    # Guardrails for LLM cost and runtime on very large documents.
    max_chunks = min(len(chunks), max(1, safe_max_rules * 2))
    effective_chunks = chunks[:max_chunks]
    if "wizard" in [str(t).strip().lower() for t in selected_types]:
        # Wizard extraction benefits from broader context per step; keep chunk count tighter.
        effective_chunks = effective_chunks[:2]

    total_chunks = len(effective_chunks)
    if total_chunks <= 0:
        return []

    per_chunk = max(1, safe_max_rules // total_chunks)
    remainder = safe_max_rules - (per_chunk * total_chunks)

    merged: list[dict] = []
    for idx, chunk in enumerate(effective_chunks):
        chunk_max = per_chunk + (1 if idx < remainder else 0)
        chunk_max = max(1, min(chunk_max, safe_max_rules))
        extracted = await extract_rules_multi_pipeline(
            chunk,
            rule_types=selected_types,
            max_rules=chunk_max,
            wizard_name=wizard_name,
            wizard_description=wizard_description,
            wizard_step_title=wizard_step_title,
            wizard_step_description=wizard_step_description,
            wizard_step_snippet=wizard_step_snippet,
            wizard_step_no=wizard_step_no,
            wizard_total_steps=wizard_total_steps,
            template_use_ai=template_use_ai,
            created_by=created_by,
        )
        for rule in extracted:
            rule["source_snippet"] = (
                f"Extracted from document: {file.filename} (chunk {idx + 1}/{total_chunks})"
            )
        merged.extend(extracted)
        merged = _dedupe_rules(merged)
        if len(merged) >= safe_max_rules:
            break

    return merged[:safe_max_rules]


def extract_text_from_pdf(file_bytes):
    text = ""
    with fitz.open(stream=file_bytes, filetype="pdf") as doc:
        for page in doc:
            text += page.get_text("text") + "\n"
    return text
