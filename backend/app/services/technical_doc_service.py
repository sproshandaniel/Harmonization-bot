from __future__ import annotations

import datetime as dt
import re
import uuid
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

from app.services.store_service import (
    get_ai_model_name,
    get_model_api_key,
    log_llm_usage_event,
)

BASE_DIR = Path(__file__).resolve().parents[2]
load_dotenv(dotenv_path=BASE_DIR / ".env", override=True)

_OPENAI_CLIENT: OpenAI | None = None
_OPENAI_CLIENT_KEY = ""


def _get_openai_client() -> OpenAI | None:
    global _OPENAI_CLIENT, _OPENAI_CLIENT_KEY
    api_key = get_model_api_key()
    if not api_key:
        _OPENAI_CLIENT = None
        _OPENAI_CLIENT_KEY = ""
        return None
    if _OPENAI_CLIENT is not None and _OPENAI_CLIENT_KEY == api_key:
        return _OPENAI_CLIENT
    try:
        _OPENAI_CLIENT = OpenAI(api_key=api_key)
        _OPENAI_CLIENT_KEY = api_key
        return _OPENAI_CLIENT
    except Exception:
        _OPENAI_CLIENT = None
        _OPENAI_CLIENT_KEY = ""
        return None


def _extract_usage_tokens(usage: Any) -> tuple[int, int, int]:
    if usage is None:
        return 0, 0, 0
    if isinstance(usage, dict):
        in_tokens = int(usage.get("input_tokens") or usage.get("prompt_tokens") or 0)
        out_tokens = int(usage.get("output_tokens") or usage.get("completion_tokens") or 0)
        total_tokens = int(usage.get("total_tokens") or 0)
    else:
        in_tokens = int(getattr(usage, "input_tokens", 0) or getattr(usage, "prompt_tokens", 0) or 0)
        out_tokens = int(getattr(usage, "output_tokens", 0) or getattr(usage, "completion_tokens", 0) or 0)
        total_tokens = int(getattr(usage, "total_tokens", 0) or 0)
    if total_tokens <= 0:
        total_tokens = max(0, in_tokens) + max(0, out_tokens)
    return max(0, in_tokens), max(0, out_tokens), max(0, total_tokens)


def _slug(text: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "-", (text or "").strip()).strip("-").lower()
    return cleaned or "document"


def _extract_changed_blocks(code: str, max_lines: int = 40) -> str:
    lines = [line.rstrip() for line in (code or "").splitlines() if line.strip()]
    if not lines:
        return ""
    return "\n".join(lines[:max_lines])


def _fallback_doc(
    object_name: str,
    code: str,
    change_summary: str | None = None,
    validation_summary: str | None = None,
) -> str:
    changed = _extract_changed_blocks(code)
    return "\n".join(
        [
            f"# Technical Design: {object_name}",
            "",
            "## Purpose",
            change_summary or "Describe business purpose and reason for change.",
            "",
            "## Changed Components",
            f"- Object: `{object_name}`",
            "- Transport: ADT",
            "",
            "## Implementation Notes",
            validation_summary or "Validation completed in CodeBot activation flow.",
            "",
            "## Current Change Snippet",
            "```abap",
            changed or "*No code snippet available*",
            "```",
            "",
            "## Testing",
            "- Unit/integration checks executed by developer",
            "- Activation and governance validation passed",
            "",
            "## Risks and Rollback",
            "- Identify dependent objects before import",
            "- Keep rollback transport ready if productive issue occurs",
        ]
    ).strip()


def _llm_generate(
    *,
    mode: str,
    object_name: str,
    code: str,
    developer: str,
    change_summary: str | None = None,
    validation_summary: str | None = None,
    existing_document: str | None = None,
) -> tuple[str, str, list[str]]:
    client = _get_openai_client()
    if client is None:
        warnings = ["OPENAI_API_KEY/model_api_key not configured; generated deterministic fallback document."]
        return _fallback_doc(object_name, code, change_summary, validation_summary), "fallback", warnings

    model = get_ai_model_name(default="gpt-4o-mini")
    prompt = f"""
You are a senior SAP ABAP technical writer.

Task mode: {mode}

Rules:
- Output only the final technical document in Markdown.
- Be precise and grounded only in provided inputs.
- If information is missing, write "Needs confirmation:" for that detail.
- Keep sections concise and practical.

Required sections:
1) Purpose
2) Technical Design
3) Changed Components
4) Data/Interface Impact
5) Validation and Testing
6) Risks and Rollback

Context:
- Object Name: {object_name}
- Developer: {developer}
- Change Summary: {change_summary or ""}
- Validation Summary: {validation_summary or ""}

Current ABAP code:
```abap
{code or ""}
```

Existing technical document (optional, enrich/update this if mode is enrich):
```markdown
{existing_document or ""}
```
""".strip()

    completion = client.responses.create(
        model=model,
        input=prompt,
        temperature=0.2,
        max_output_tokens=2200,
    )
    in_tokens, out_tokens, total_tokens = _extract_usage_tokens(getattr(completion, "usage", None))
    if total_tokens > 0:
        log_llm_usage_event(
            developer=developer,
            feature="technical_document_generation",
            provider="openai",
            model=model,
            input_tokens=in_tokens,
            output_tokens=out_tokens,
            total_tokens=total_tokens,
            metadata={"mode": mode, "object_name": object_name},
        )
    doc_text = (completion.output_text or "").strip()
    if not doc_text:
        return _fallback_doc(object_name, code, change_summary, validation_summary), "fallback", [
            "LLM returned empty output; fallback document generated."
        ]
    return doc_text, model, []


def generate_technical_doc(
    *,
    code: str,
    object_name: str,
    developer: str,
    change_summary: str | None = None,
    validation_summary: str | None = None,
) -> dict[str, Any]:
    doc_text, model_used, warnings = _llm_generate(
        mode="generate",
        object_name=object_name,
        code=code,
        developer=developer,
        change_summary=change_summary,
        validation_summary=validation_summary,
    )
    return {
        "title": f"Technical Design - {object_name}",
        "document": doc_text,
        "model_used": model_used,
        "warnings": warnings,
    }


def enrich_technical_doc(
    *,
    existing_document: str,
    code: str,
    object_name: str,
    developer: str,
    change_summary: str | None = None,
    validation_summary: str | None = None,
) -> dict[str, Any]:
    doc_text, model_used, warnings = _llm_generate(
        mode="enrich",
        object_name=object_name,
        code=code,
        developer=developer,
        change_summary=change_summary,
        validation_summary=validation_summary,
        existing_document=existing_document,
    )
    return {
        "title": f"Technical Design - {object_name}",
        "document": doc_text,
        "model_used": model_used,
        "warnings": warnings,
    }


def save_technical_doc(
    *,
    title: str,
    document: str,
    object_name: str,
    developer: str,
    project_id: str | None = None,
) -> dict[str, Any]:
    target_dir = BASE_DIR / "data" / "technical_docs"
    target_dir.mkdir(parents=True, exist_ok=True)

    ts = dt.datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    project_part = _slug(project_id or "default")
    object_part = _slug(object_name or "adt-object")
    doc_id = f"doc-{uuid.uuid4().hex[:10]}"
    filename = f"{project_part}-{object_part}-{ts}-{doc_id}.md"
    path = target_dir / filename

    header = "\n".join(
        [
            f"<!-- title: {title or 'Technical Design'} -->",
            f"<!-- object_name: {object_name or 'ADT_OBJECT'} -->",
            f"<!-- developer: {developer or 'unknown'} -->",
            f"<!-- project_id: {project_id or ''} -->",
            f"<!-- saved_at_utc: {dt.datetime.utcnow().isoformat()}Z -->",
            "",
        ]
    )
    path.write_text(header + (document or "").strip() + "\n", encoding="utf-8")

    return {
        "doc_id": doc_id,
        "saved_path": str(path),
        "title": title or "Technical Design",
    }
