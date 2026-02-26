from __future__ import annotations

import datetime as dt
import re
import uuid
from pathlib import Path
from typing import Any

_DOC_META_PATTERN = re.compile(r"^<!--\s*([a-zA-Z0-9_]+)\s*:\s*(.*?)\s*-->$")

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


def _derive_change_summary(code: str) -> str:
    lines = [line.strip() for line in (code or "").splitlines() if line.strip()]
    if not lines:
        return "No active code lines were available in the editor."
    declared = [ln for ln in lines if ln.lower().startswith("data")]
    has_try = any(ln.upper().startswith("TRY") for ln in lines)
    has_catch = any(ln.upper().startswith("CATCH") for ln in lines)
    has_assignment = any("=" in ln and not ln.upper().startswith(("TRY", "CATCH", "ENDTRY")) for ln in lines)

    summary_parts: list[str] = []
    if declared:
        summary_parts.append("Added or updated local variable declarations.")
    if has_assignment:
        summary_parts.append("Updated arithmetic/assignment logic in the implementation block.")
    if has_try or has_catch:
        summary_parts.append("Wrapped arithmetic logic in exception handling to guard runtime overflow.")
    if not summary_parts:
        summary_parts.append("Updated ABAP implementation logic in the current editor object.")
    return " ".join(summary_parts)


def _derive_pseudocode(code: str) -> str:
    lines = [line.strip() for line in (code or "").splitlines() if line.strip()]
    if not lines:
        return "- Read current editor code\n- Identify changed statements\n- Apply logic changes\n- Handle runtime exceptions where required"
    pseudo: list[str] = []
    for ln in lines[:20]:
        upper = ln.upper()
        if upper.startswith("DATA"):
            pseudo.append("- Declare working variables")
        elif upper.startswith("TRY"):
            pseudo.append("- Start protected execution block")
        elif upper.startswith("CATCH"):
            pseudo.append("- Catch arithmetic overflow and prevent dump")
        elif upper.startswith("ENDTRY"):
            pseudo.append("- End protected execution block")
        elif "=" in ln:
            pseudo.append(f"- Compute and assign value: `{ln.rstrip('.')}`")
    deduped: list[str] = []
    for item in pseudo:
        if item not in deduped:
            deduped.append(item)
    return "\n".join(deduped) if deduped else "- Apply implementation changes based on current editor code"


def _fallback_doc(
    object_name: str,
    code: str,
    change_summary: str | None = None,
    validation_summary: str | None = None,
) -> str:
    changed = _extract_changed_blocks(code)
    resolved_summary = (change_summary or "").strip() or _derive_change_summary(code)
    pseudocode = _derive_pseudocode(code)
    return "\n".join(
        [
            f"# Technical Design: {object_name}",
            "",
            "## Purpose",
            resolved_summary,
            "",
            "## Short Change Summary",
            resolved_summary,
            "",
            "## Pseudocode of Changes",
            pseudocode,
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
Act as a senior SAP technical architect and documentation specialist.

Task mode: {mode}

Generate COMPLETE technical documentation in Markdown with exactly these sections:

====================================================================
1. PURPOSE OF CHANGE
====================================================================

Include implementation-aligned detail:
- Business problem being solved
- Technical objective
- Scope of processing
- Data objects involved (tables, structures, infotypes, function modules, classes)
- Control logic overview
- Impact on existing functionality
- Data consistency implications
- Performance considerations
- Risk considerations
- Output/result of the program

====================================================================
2. DETAILED TEXT FLOWCHART (Step-by-Step Execution Logic)
====================================================================

Use explicit control-flow text with this style:
START
  ↓
Step
  ↓
Decision? (condition)
  ├─ YES → Action
  └─ NO  → Action
  ↓
Next step

Mandatory in flowchart:
- Cover each SELECT, LOOP, GROUP BY, IF/ELSEIF/ELSE, CHECK
- Cover CALL FUNCTION and method calls
- Cover DELETE/UPDATE/INSERT and COMMIT WORK
- Cover exception handling and SY-SUBRC checks
- Expand nested loops hierarchically
- Show counter increments, continue/return/exit paths, and error branches
- Separate DB reads from DB writes
- Do not summarize or skip minor conditions

====================================================================
3. GRAPHICAL FLOWCHART (Mermaid Diagram)
====================================================================

Provide a Mermaid flowchart representing the same logic as the text flowchart:
- Include Start/End, loops, decisions, DB operations, function calls, write operations
- Include YES/NO decision branches
- Ensure loops reconnect properly and nested loops are traceable
- Do not omit branches

Rules:
- Use exact SAP object names from input
- Avoid hallucinations; if assumptions are needed, state them explicitly
- Ground every statement in the provided code/context

Context:
- Object Name: {object_name}
- Developer: {developer}
- Change Summary: {change_summary or ""}
- Validation Summary: {validation_summary or ""}

ABAP OBJECT:
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



def _read_doc_payload(path: Path) -> dict[str, Any] | None:
    try:
        raw = path.read_text(encoding="utf-8")
    except Exception:
        return None

    metadata: dict[str, str] = {}
    lines = raw.splitlines()
    content_start = 0
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            content_start = i + 1
            continue
        match = _DOC_META_PATTERN.match(stripped)
        if not match:
            content_start = i
            break
        metadata[match.group(1).strip().lower()] = match.group(2).strip()
        content_start = i + 1

    body = "\n".join(lines[content_start:]).strip()
    file_match = re.search(r"(doc-[a-f0-9]{10})\.md$", path.name)
    doc_id = metadata.get("doc_id") or (file_match.group(1) if file_match else "")
    saved_at = metadata.get("saved_at_utc")
    if not saved_at:
        saved_at = dt.datetime.utcfromtimestamp(path.stat().st_mtime).isoformat() + "Z"

    return {
        "doc_id": doc_id,
        "title": metadata.get("title") or "Technical Design",
        "object_name": metadata.get("object_name") or "ADT_OBJECT",
        "developer": metadata.get("developer") or "",
        "project_id": metadata.get("project_id") or "",
        "saved_at_utc": saved_at,
        "saved_path": str(path),
        "document": body,
    }


def _value_matches(candidate: str, expected: str | None) -> bool:
    if expected is None or not expected.strip():
        return True
    return (candidate or "").strip().lower() == expected.strip().lower()


def load_latest_technical_doc(
    *,
    object_name: str | None = None,
    developer: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any] | None:
    target_dir = BASE_DIR / "data" / "technical_docs"
    if not target_dir.exists():
        return None

    files = sorted(target_dir.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    for path in files:
        payload = _read_doc_payload(path)
        if payload is None:
            continue
        if not _value_matches(str(payload.get("object_name") or ""), object_name):
            continue
        if not _value_matches(str(payload.get("project_id") or ""), project_id):
            continue
        if not _value_matches(str(payload.get("developer") or ""), developer):
            continue
        if not str(payload.get("document") or "").strip():
            continue
        return payload
    return None
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
            f"<!-- doc_id: {doc_id} -->",
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
