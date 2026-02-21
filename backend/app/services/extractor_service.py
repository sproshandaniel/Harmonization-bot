"""
Rule Extraction Pipeline
------------------------
Uses OpenAI GPT for rule synthesis and Qdrant for duplicate detection.
"""

from __future__ import annotations

import re
import json
import hashlib
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
from openai import OpenAI

from app.services.store_service import get_ai_model_name, get_model_api_key, log_llm_usage_event
from app.services.vector_store_service import find_duplicate_rule, upsert_rule_vector

BASE_DIR = Path(__file__).resolve().parents[2]
load_dotenv(dotenv_path=BASE_DIR / ".env", override=True)

_OPENAI_CLIENT = None
_OPENAI_CLIENT_KEY = ""
ALLOWED_RULE_TYPES = {"code", "design", "template", "wizard"}
ALLOWED_SEVERITIES = {"MAJOR", "MINOR", "INFO"}
CODE_SUBTAGS = ("code", "naming", "performance")


def _normalize_requested_rule_type(value: str | None) -> str:
    text = str(value or "").strip().lower()
    aliases = {
        "coe": "code",
        "coding": "code",
        "perf": "performance",
    }
    text = aliases.get(text, text)
    if text in {"naming", "performance"}:
        return "code"
    if text in {"code", "design", "template", "wizard"}:
        return text
    return "code"


def _normalize_code_subtags(value: Any) -> list[str]:
    items: list[str] = []
    if isinstance(value, list):
        items = [str(v or "").strip().lower() for v in value]
    elif isinstance(value, str):
        items = [part.strip().lower() for part in value.split(",")]

    out: list[str] = []
    for item in items:
        if item in {"coe", "coding"}:
            item = "code"
        if item == "perf":
            item = "performance"
        if item in CODE_SUBTAGS and item not in out:
            out.append(item)
    return out


def _derive_code_subtags(
    rule_obj: dict[str, Any],
    fallback_type: str,
    title: str,
    description: str,
    message: str,
    fix: str,
    rationale: str,
) -> list[str]:
    subtags = _normalize_code_subtags(rule_obj.get("subtags"))
    if "code" not in subtags:
        subtags.insert(0, "code")

    lowered_text = " ".join([title, description, message, fix, rationale]).lower()
    naming_hint = bool(
        re.search(r"\b(name|naming|prefix|suffix|convention|camel|snake)\b", lowered_text)
    )
    performance_hint = bool(
        re.search(r"\b(performance|optimi[sz]e|efficient|select\s+\*|for all entries|index|loop)\b", lowered_text)
    )

    if str(fallback_type).lower().strip() == "naming" and "naming" not in subtags:
        subtags.append("naming")
    if str(fallback_type).lower().strip() == "performance" and "performance" not in subtags:
        subtags.append("performance")
    if naming_hint and "naming" not in subtags:
        subtags.append("naming")
    if performance_hint and "performance" not in subtags:
        subtags.append("performance")

    ordered = ["code", "naming", "performance"]
    return [tag for tag in ordered if tag in subtags]


def _get_openai_client():
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

EXTRACTION_PROMPT = """
You are an ABAP coding standards expert.

Task:
- Extract enforceable coding standards from the provided ABAP code/document.
- Propose up to {max_rules} standards as rules.
- Honor the requested rule type: {rule_type}.
- STRICT TYPE RULE: Every generated rule MUST use exactly type: "{rule_type}".
- DO NOT output any rule with other types (code/design/template/wizard) unless it equals "{rule_type}".
- If uncertain, still set type to "{rule_type}" and adapt the title/description to that type.
- If type is "code", include `subtags` with one or more of: code, naming, performance.
- Focus on governance standards and best practices:
  - design patterns (singleton/factory/strategy)
  - class visibility and constructor constraints
  - exception handling
  - naming conventions
  - SQL/performance safety
  - template reuse and snippet quality
- Each rule must be specific, testable, and implementation-ready.
- The selector.pattern must be a robust validation signature that matches likely
  NON-compliant code, not just a generic label.
- Prefer regex-friendly patterns that are stable across variable names and formatting.
- If the rule says certain constructs are required (e.g. TRY...CATCH), choose a
  selector.pattern that matches the risky operation to scan (e.g. arithmetic assignment),
  so validator can detect missing required wrappers.

Return ONLY valid YAML in this exact shape:
rules:
  - id: "<stable.rule.id>"
    type: "{rule_type}"
    subtags: ["code|naming|performance"] # required only when type is code
    title: "<short title>"
    severity: "MAJOR|MINOR|INFO"
    description: "<what this rule enforces>"
    message: "<clear violation message shown to developers when code fails this rule>"
    selector:
      pattern: "<validation selector pattern, regex-friendly>"
    fix: "<recommended fix>"
    rationale: "<why this matters>"
    example:
      bad: |
        <short non-compliant ABAP example>
      good: |
        <short compliant ABAP example>
    confidence: <0.0-1.0>
"""

CODE_GROUNDING_PROMPT = """
Additional strict grounding rules for type "code":
- Generate rules ONLY from constructs explicitly present in the provided input.
- Do NOT invent SQL, class-definition, constructor, or visibility rules unless those constructs appear in input.
- If input is a method/function call snippet, prefer API-usage, parameter, and call-safety rules grounded to that call.
- selector.pattern must match the provided input (or likely non-compliant variants of the same construct).
"""

WIZARD_EXTRACTION_PROMPT = """
You are an ABAP solution architect.

Task:
- Build a development wizard from the provided ABAP requirement/code/document.
- A wizard is a sequence of implementation steps for multiple objects.
- Generate up to {max_rules} steps.
- Each step must include a template snippet that guides implementation.
- The selector.pattern must be a short, specific search phrase that a chatbot can
  use to identify this wizard step (e.g., "wizard factory pattern step 1",
  "create singleton class", "define RAP behavior").
- STRICT TYPE RULE: Every generated step MUST use exactly type: "wizard".
- DO NOT output code/design/naming/performance/template types in wizard mode.

Return ONLY valid YAML in this exact shape:
rules:
  - id: "wizard.<topic>.step.<n>"
    type: "wizard"
    title: "<step title>"
    severity: "MAJOR|MINOR|INFO"
    description: "<what this step enforces>"
    message: "<clear violation message shown when this step is not followed>"
    selector:
      pattern: "<detection pattern for this step>"
    fix: "<recommended fix>"
    rationale: "<why this step matters>"
    confidence: <0.0-1.0>
    wizard:
      step_no: <integer starting at 1>
      step_title: "<short step title>"
      object_type: "<ABAP object type like class/report/function group/table>"
      depends_on: [<step numbers this step depends on>]
      template:
        language: "ABAP"
        snippet: |
          <ABAP template snippet for this step>
"""


def _extract_abap_object_names(text: str) -> list[str]:
    matches: list[str] = []
    for pattern in [
        r"\bCLASS\s+([A-Z0-9_]+)\b",
        r"\bINTERFACE\s+([A-Z0-9_]+)\b",
        r"\bFUNCTION\s+([A-Z0-9_]+)\b",
        r"\bREPORT\s+([A-Z0-9_]+)\b",
        r"\bFORM\s+([A-Z0-9_]+)\b",
    ]:
        matches += re.findall(pattern, text, flags=re.IGNORECASE)
    return [m for m in matches if m]


def _derive_selector_pattern(
    rule_type: str,
    title: str,
    description: str,
    raw_text: str,
    wizard_name: str | None = None,
    wizard_step_title: str | None = None,
    object_type: str | None = None,
) -> str:
    title = title.strip()
    description = description.strip()
    if rule_type == "template":
        names = _extract_abap_object_names(raw_text)
        if names:
            return f"{names[0]} template"
        if title:
            return title
        if description:
            return description[:80]
        return "abap template"
    if rule_type == "wizard":
        parts = [wizard_name or "", wizard_step_title or "", object_type or ""]
        pattern = " ".join([p.strip() for p in parts if p and p.strip()])
        return pattern or title or description[:80] or "wizard step"
    return title or description[:80] or "abap rule"


def _sanitize_template_snippet(snippet: str) -> str:
    text = str(snippet or "").replace("\r\n", "\n").strip()
    if not text:
        return text
    lines = text.splitlines()
    # Drop trailing ENDIF when snippet was copied from a larger context block.
    if lines and lines[-1].strip().upper() == "ENDIF.":
        has_if_open = any(re.search(r"\bIF\b", line, flags=re.IGNORECASE) for line in lines[:-1])
        if not has_if_open:
            lines = lines[:-1]
    cleaned = "\n".join(lines).strip()
    # Normalize accidental doubled terminator in copied snippets: )..
    cleaned = re.sub(r"\)\.\.+", ").", cleaned)
    return cleaned


def _derive_template_selector_pattern(snippet: str, title: str, description: str) -> str:
    source = f"{snippet}\n{title}\n{description}"
    method_call = re.search(r"\b([A-Z0-9_]+)=>([A-Z0-9_]+)\s*\(", source, flags=re.IGNORECASE)
    if method_call:
        return f"{method_call.group(1)}=>{method_call.group(2)}"
    class_decl = re.search(r"\bCLASS\s+([A-Z0-9_]+)\b", source, flags=re.IGNORECASE)
    if class_decl:
        return class_decl.group(1)
    function_call = re.search(r"\bCALL\s+FUNCTION\s+'?([A-Z0-9_]+)'?\b", source, flags=re.IGNORECASE)
    if function_call:
        return function_call.group(1)
    names = _extract_abap_object_names(source)
    if names:
        return names[0]
    slug = re.sub(r"[^A-Za-z0-9_]+", " ", title).strip()
    return slug or "abap_template"


def _template_code_signature(snippet: str, selector_pattern: str) -> str:
    source = str(snippet or "").strip()
    if not source:
        return str(selector_pattern or "").strip() or "abap_template"

    method_call = re.search(r"\b([A-Z0-9_]+)=>([A-Z0-9_]+)\s*\(", source, flags=re.IGNORECASE)
    if method_call:
        return f"{method_call.group(1)}=>{method_call.group(2)}"

    function_call = re.search(r"\bCALL\s+FUNCTION\s+'?([A-Z0-9_]+)'?\b", source, flags=re.IGNORECASE)
    if function_call:
        return f"CALL FUNCTION {function_call.group(1)}"

    class_decl = re.search(r"\bCLASS\s+([A-Z0-9_]+)\b", source, flags=re.IGNORECASE)
    if class_decl:
        return f"CLASS {class_decl.group(1)}"

    method_decl = re.search(r"\bMETHOD\s+([A-Z0-9_]+)\b", source, flags=re.IGNORECASE)
    if method_decl:
        return f"METHOD {method_decl.group(1)}"

    for line in source.splitlines():
        cleaned = line.strip()
        if not cleaned:
            continue
        cleaned = re.sub(r"\s+", " ", cleaned)
        return cleaned[:72]
    return str(selector_pattern or "").strip() or "abap_template"


def _collect_template_intent_terms(selector_pattern: str, snippet: str) -> list[str]:
    source = f"{selector_pattern}\n{snippet}".lower()
    words = re.findall(r"[a-z0-9_]{2,}", source)
    raw_terms = set()
    for word in words:
        for part in word.split("_"):
            part = part.strip()
            if len(part) >= 2:
                raw_terms.add(part)

    term_map = {
        "emp": "employee",
        "employees": "employee",
        "employee": "employee",
        "mgr": "manager",
        "manager": "manager",
        "mss": "manager",
        "reportee": "reportee",
        "reportees": "reportee",
        "active": "active",
        "pernr": "personnel",
        "role": "role",
        "teamviewer": "team",
        "team": "team",
        "get": "retrieve",
        "fetch": "retrieve",
        "retrieve": "retrieve",
    }

    normalized = []
    for raw in raw_terms:
        mapped = term_map.get(raw, raw)
        if mapped in {"abap", "type", "data", "iv", "ev", "lt", "gv", "zcl", "reuse"}:
            continue
        if len(mapped) < 3:
            continue
        normalized.append(mapped)

    priority = [
        "employee",
        "manager",
        "reportee",
        "retrieve",
        "active",
        "personnel",
        "role",
        "team",
    ]
    ordered = []
    for p in priority:
        if p in normalized and p not in ordered:
            ordered.append(p)
    for item in sorted(set(normalized)):
        if item not in ordered:
            ordered.append(item)
    return ordered[:8]


def _infer_template_scope(text: str) -> str:
    lowered = (text or "").lower()
    if any(term in lowered for term in ("manager", "reportee", "teamviewer", "mss")):
        return "manager"
    if any(term in lowered for term in ("org", "organization", "team")):
        return "org"
    return "self"


def _infer_template_intent(text: str) -> str:
    lowered = (text or "").lower()
    if any(term in lowered for term in ("country", "molga", "land1", "nationality")):
        return "get_country"
    if any(term in lowered for term in ("manager", "reportee", "teamviewer", "mss")):
        return "get_manager_team"
    if any(term in lowered for term in ("employee", "pernr", "personnel")):
        return "get_employee"
    return "generic_template"


def _normalize_template_rule(
    rule_obj: dict[str, Any],
    idx: int,
    raw_text: str | None = None,
) -> dict[str, Any]:
    template_block = rule_obj.get("template")
    if not isinstance(template_block, dict):
        template_block = {}

    snippet = str(template_block.get("snippet") or "").strip()
    if not snippet and raw_text:
        snippet = str(raw_text).strip()
    snippet = _sanitize_template_snippet(snippet)

    title = str(rule_obj.get("title") or "").strip()
    description = str(rule_obj.get("description") or "").strip()
    selector_pattern = _derive_template_selector_pattern(snippet, title, description)
    code_signature = _template_code_signature(snippet, selector_pattern)
    intent_terms = _collect_template_intent_terms(selector_pattern, snippet)
    intent_text = ", ".join(intent_terms[:5]) if intent_terms else "general reusable ABAP operations"

    # Remove validation-rule phrasing from template metadata.
    rule_like_text = f"{title}\n{description}"
    if re.search(r"\b(try|catch|exception|violation|risky)\b", rule_like_text, flags=re.IGNORECASE):
        title = ""
        description = ""

    if not title:
        title = f"Template: {selector_pattern} [{code_signature}]"
    elif code_signature and code_signature.lower() not in title.lower():
        title = f"{title} [{code_signature}]"
    if not description:
        description = (
            f"Reusable ABAP template snippet for {selector_pattern} ({code_signature}). "
            f"Useful for requests about {intent_text}."
        )
    elif code_signature and code_signature.lower() not in description.lower():
        description = f"{description} Primary code signature: {code_signature}."
    combined_text = "\n".join([title, description, selector_pattern, snippet]).lower()
    scope = _infer_template_scope(combined_text)
    intent = _infer_template_intent(combined_text)
    entities = [term for term in ("employee", "manager", "reportee") if term in combined_text]
    domain_fields = [
        term
        for term in ("molga", "country", "land1", "pernr", "personnel")
        if term in combined_text
    ]

    confidence = rule_obj.get("confidence", 0.9)
    try:
        confidence = float(confidence)
    except Exception:
        confidence = 0.9
    if confidence > 1.0 and confidence <= 100.0:
        confidence = confidence / 100.0
    confidence = max(0.0, min(1.0, confidence))

    hash_part = hashlib.sha1(snippet.encode("utf-8", "ignore")).hexdigest()[:10] if snippet else str(idx)
    search_slug = _slug_for_id(f"{selector_pattern}.{code_signature}")[:48]
    default_id = (
        f"abap.template.{search_slug}.{hash_part}"
        if snippet
        else f"abap.template.{idx}"
    )
    incoming_id = str(rule_obj.get("id") or "").strip().lower()
    keep_incoming_template_id = (
        bool(incoming_id)
        and incoming_id.startswith("abap.template.")
        and "exception" not in incoming_id
        and "try_catch" not in incoming_id
    )
    rule_id = incoming_id if keep_incoming_template_id else default_id

    return {
        "id": rule_id,
        "type": "template",
        "title": title,
        "severity": "INFO",
        "description": description,
        "selector": {"pattern": selector_pattern},
        "fix": "Reuse this approved ABAP template.",
        "rationale": (
            "Template reuse improves consistency and maintainability. "
            f"Keywords: {intent_text}."
        ),
        "confidence": confidence,
        "metadata": {
            "intent": intent,
            "scope": scope,
            "entities": entities,
            "domain_fields": domain_fields,
            "keywords": intent_terms,
            "source_type": "template",
            "confidence": confidence,
            "code_signature": code_signature,
        },
        "template": {
            "language": "ABAP",
            "snippet": snippet,
        },
    }


def _derive_validation_selector_pattern(
    rule_type: str,
    title: str,
    description: str,
    raw_text: str,
    good_example: str = "",
    bad_example: str = "",
) -> str:
    combined = "\n".join([title, description, raw_text, good_example, bad_example]).upper()

    # Common robust validation signatures for ABAP governance rules.
    has_try_catch = ("TRY." in combined or "TRY" in combined) and ("CATCH" in combined or "ENDTRY." in combined)
    has_arithmetic = bool(
        re.search(r"\b[A-Z0-9_]+\b\s*=\s*[^.\n]*[+\-*/][^.\n]*\.", combined)
    ) or any(word in combined for word in ["ARITH", "OVERFLOW", "CALCULATION", "NUMERIC"])
    if rule_type in {"code", "design", "performance"} and has_try_catch and has_arithmetic:
        return r"\b[A-Z0-9_]+\b\s*=\s*[^.\n]*[+\-*/][^.\n]*\."

    if "SELECT *" in combined:
        return r"\bSELECT\s+\*\s+FROM\b"
    if "FOR ALL ENTRIES" in combined and "IS INITIAL" in combined:
        return r"\bFOR\s+ALL\s+ENTRIES\s+IN\b"
    if "COMMIT WORK" in combined and "LOOP" in combined:
        return r"\bCOMMIT\s+WORK\b"

    return _derive_selector_pattern(
        rule_type=rule_type,
        title=title,
        description=description,
        raw_text=raw_text,
    )


def detect_category(text: str) -> str:
    up = text.upper()
    if "WIZARD" in up or ("STEP" in up and "OBJECT" in up):
        return "wizard"
    if any(k in up for k in ["SELECT", "TRY.", "METHOD", "CALL FUNCTION"]):
        return "code"
    if "DESIGN" in up or "PATTERN" in up:
        return "design"
    if "NAME" in up or "PREFIX" in up:
        return "code"
    if "PERFORMANCE" in up or "OPTIMIZE" in up:
        return "code"
    if "TEMPLATE" in up or "SNIPPET" in up:
        return "template"
    return "code"


def _build_prompt(
    raw_text: str,
    rule_type: str,
    max_rules: int,
    wizard_name: str | None = None,
    wizard_description: str | None = None,
    wizard_step_title: str | None = None,
    wizard_step_description: str | None = None,
    wizard_step_no: int | None = None,
    wizard_total_steps: int | None = None,
) -> str:
    detected = detect_category(raw_text)
    normalized = rule_type if rule_type else detected
    if normalized == "wizard":
        base = WIZARD_EXTRACTION_PROMPT.format(max_rules=max_rules)
        if wizard_name and wizard_name.strip():
            base += f"\n\nWizard Name:\n{wizard_name.strip()}"
        if wizard_description and wizard_description.strip():
            base += f"\n\nWizard Description:\n{wizard_description.strip()}"
        if wizard_total_steps is not None:
            base += f"\n\nTotal Steps:\n{wizard_total_steps}"
        if wizard_step_no is not None:
            base += f"\n\nCurrent Step Number:\n{wizard_step_no}"
        if wizard_step_title and wizard_step_title.strip():
            base += f"\n\nStep Title:\n{wizard_step_title.strip()}"
        if wizard_step_description and wizard_step_description.strip():
            base += f"\n\nStep Description:\n{wizard_step_description.strip()}"
    else:
        base = EXTRACTION_PROMPT.format(rule_type=normalized, max_rules=max_rules)
        if normalized == "code":
            base = f"{base}\n\n{CODE_GROUNDING_PROMPT.strip()}"
    return f"{base}\n\nInput:\n{raw_text[:8000]}"


def _safe_rule_yaml(rule_obj: dict[str, Any]) -> str:
    return yaml.safe_dump(rule_obj, sort_keys=False, width=120)


def _ensure_template_snippet_yaml(rule_yaml: str, raw_text: str) -> str:
    try:
        parsed = yaml.safe_load(rule_yaml)
    except Exception:
        return rule_yaml
    if not isinstance(parsed, dict):
        return rule_yaml
    if str(parsed.get("type", "")).lower() != "template":
        return rule_yaml
    normalized = _normalize_template_rule(parsed, idx=1, raw_text=raw_text)
    return yaml.safe_dump(normalized, sort_keys=False, width=120)


def _slug_for_id(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", ".", value.lower()).strip(".")
    return slug or "wizard"


def _default_good_example(rule_type: str) -> str:
    if rule_type == "performance":
        return (
            "SELECT pernr persg\n"
            "  FROM pa0001\n"
            "  INTO TABLE @DATA(lt_pa0001)\n"
            "  WHERE pernr = @lv_pernr."
        )
    if rule_type == "naming":
        return (
            "CLASS zcl_employee_service DEFINITION PUBLIC FINAL CREATE PUBLIC.\n"
            "  PUBLIC SECTION.\n"
            "    METHODS get_employee_data.\n"
            "ENDCLASS."
        )
    if rule_type == "design":
        return (
            "TRY.\n"
            "    lo_service->execute( ).\n"
            "  CATCH cx_root INTO DATA(lx_error).\n"
            "    \" handle gracefully\n"
            "ENDTRY."
        )
    return (
        "METHOD process_data.\n"
        "  TRY.\n"
        "      lv_total = lv_amount1 + lv_amount2.\n"
        "    CATCH cx_root.\n"
        "      lv_total = 0.\n"
        "  ENDTRY.\n"
        "ENDMETHOD."
    )


def _extract_good_example(rule_obj: dict[str, Any], normalized_type: str) -> str:
    example_block = rule_obj.get("example")
    if isinstance(example_block, dict):
        for key in ("good", "good_code", "example_good_code", "compliant"):
            value = str(example_block.get(key) or "").strip()
            if value:
                return value
    direct_keys = ("good_example", "example_good_code", "good_code", "compliant_example")
    for key in direct_keys:
        value = str(rule_obj.get(key) or "").strip()
        if value:
            return value
    fix_text = str(rule_obj.get("fix") or "").strip()
    if "\n" in fix_text:
        return fix_text
    return _default_good_example(normalized_type)


def _extract_bad_example(rule_obj: dict[str, Any]) -> str:
    example_block = rule_obj.get("example")
    if isinstance(example_block, dict):
        for key in ("bad", "bad_code", "example_bad_code", "non_compliant"):
            value = str(example_block.get(key) or "").strip()
            if value:
                return value
    for key in ("bad_example", "example_bad_code", "bad_code", "non_compliant_example"):
        value = str(rule_obj.get(key) or "").strip()
        if value:
            return value
    return ""


def _coerce_rule(
    rule_obj: dict[str, Any],
    fallback_type: str,
    idx: int,
    wizard_name: str | None = None,
    wizard_description: str | None = None,
    wizard_step_title: str | None = None,
    wizard_step_description: str | None = None,
    wizard_step_no: int | None = None,
    wizard_total_steps: int | None = None,
    raw_text: str | None = None,
) -> dict[str, Any]:
    rule_id = str(rule_obj.get("id") or f"rule.{fallback_type}.{idx}")
    requested_type = str(fallback_type or "").lower().strip()
    normalized_type = _normalize_requested_rule_type(requested_type)
    incoming_type = _normalize_requested_rule_type(str(rule_obj.get("type") or "").strip().lower())
    if normalized_type == "code" and incoming_type in {"design", "template", "wizard"}:
        normalized_type = incoming_type

    raw_severity = str(rule_obj.get("severity") or "MAJOR").upper().strip()
    severity_map = {
        "HIGH": "MAJOR",
        "MEDIUM": "MAJOR",
        "LOW": "MINOR",
        "WARN": "MAJOR",
        "WARNING": "MAJOR",
    }
    normalized_severity = severity_map.get(raw_severity, raw_severity)
    if normalized_severity not in ALLOWED_SEVERITIES:
        normalized_severity = "MAJOR"

    confidence = rule_obj.get("confidence", 0.7)
    try:
        confidence = float(confidence)
    except Exception:
        confidence = 0.7
    if confidence > 1.0 and confidence <= 100.0:
        confidence = confidence / 100.0

    title = str(rule_obj.get("title") or rule_obj.get("name") or f"Rule {idx}").strip()
    description = str(
        rule_obj.get("description")
        or rule_obj.get("message")
        or rule_obj.get("rationale")
        or "No description provided."
    ).strip()
    message = str(
        rule_obj.get("message")
        or f"Rule violation: {title}. {description}"
    ).strip()

    if normalized_type == "wizard":
        if wizard_step_title and wizard_step_title.strip():
            title = wizard_step_title.strip()
        if wizard_step_description and wizard_step_description.strip():
            description = wizard_step_description.strip()

    normalized_rule = {
        **rule_obj,
        "id": rule_id,
        "type": normalized_type,
        "title": title,
        "description": description,
        "severity": normalized_severity,
        "confidence": max(0.0, min(1.0, confidence)),
    }
    if normalized_type not in {"wizard", "template"}:
        normalized_rule["message"] = message
        normalized_rule["example"] = {
            "bad": _extract_bad_example(rule_obj),
            "good": _extract_good_example(rule_obj, normalized_type),
        }
        if normalized_type == "code":
            normalized_rule["subtags"] = _derive_code_subtags(
                rule_obj=rule_obj,
                fallback_type=fallback_type,
                title=title,
                description=description,
                message=message,
                fix=str(rule_obj.get("fix") or "").strip(),
                rationale=str(rule_obj.get("rationale") or "").strip(),
            )
    else:
        normalized_rule.pop("message", None)

    if normalized_type == "template":
        return _normalize_template_rule(rule_obj, idx=idx, raw_text=raw_text)
    if normalized_type == "wizard":
        wizard_block = normalized_rule.get("wizard")
        if not isinstance(wizard_block, dict):
            wizard_block = {}
        template_block = wizard_block.get("template")
        if not isinstance(template_block, dict):
            template_block = {}
        snippet = str(template_block.get("snippet") or rule_obj.get("template_snippet") or "").strip()
        if not snippet:
            snippet = "CLASS zcl_wizard_step IMPLEMENTATION.\nENDCLASS."

        step_no = wizard_step_no if wizard_step_no is not None else wizard_block.get("step_no", idx)
        try:
            step_no = int(step_no)
        except Exception:
            step_no = idx
        if step_no < 1:
            step_no = idx

        step_title = str(wizard_block.get("step_title") or title).strip()
        if wizard_step_title and wizard_step_title.strip():
            step_title = wizard_step_title.strip()
        step_description = str(wizard_block.get("step_description") or description).strip()
        if wizard_step_description and wizard_step_description.strip():
            step_description = wizard_step_description.strip()

        normalized_rule["wizard"] = {
            "step_no": step_no,
            "step_title": step_title,
            "step_description": step_description,
            "object_type": str(wizard_block.get("object_type") or "class").strip(),
            "depends_on": wizard_block.get("depends_on") if isinstance(wizard_block.get("depends_on"), list) else [],
            "template": {
                "language": str(template_block.get("language") or "ABAP").strip(),
                "snippet": snippet,
            },
        }
        if wizard_name and wizard_name.strip():
            normalized_rule["wizard"]["wizard_name"] = wizard_name.strip()
        if wizard_description and wizard_description.strip():
            normalized_rule["wizard"]["wizard_description"] = wizard_description.strip()
        if wizard_total_steps is not None:
            normalized_rule["wizard"]["total_steps"] = int(wizard_total_steps)
        if wizard_name and wizard_name.strip():
            normalized_rule["id"] = f"wizard.{_slug_for_id(wizard_name)}.step.{step_no}"

    selector = normalized_rule.get("selector")
    selector_pattern = ""
    if isinstance(selector, dict):
        selector_pattern = str(selector.get("pattern") or "").strip()
    elif isinstance(selector, str):
        selector_pattern = selector.strip()
        selector = {"pattern": selector_pattern} if selector_pattern else None

    generic_patterns = {
        "template_snippet",
        "wizard_step",
        "wizard",
        "template",
        "abap rule",
        "rule",
        "use try...catch",
    }
    needs_selector = not selector_pattern or selector_pattern.lower() in generic_patterns
    if needs_selector:
        good_example = ""
        bad_example = ""
        example_block = normalized_rule.get("example")
        if isinstance(example_block, dict):
            good_example = str(example_block.get("good") or "").strip()
            bad_example = str(example_block.get("bad") or "").strip()
        template_snippet = ""
        wizard_block = normalized_rule.get("wizard")
        if isinstance(wizard_block, dict):
            template_block = wizard_block.get("template")
            if isinstance(template_block, dict):
                template_snippet = str(template_block.get("snippet") or "")
        if normalized_type == "wizard":
            selector_pattern = _derive_selector_pattern(
                "wizard",
                title,
                description,
                raw_text=template_snippet,
                wizard_name=wizard_block.get("wizard_name") or wizard_name,
                wizard_step_title=wizard_block.get("step_title"),
                object_type=wizard_block.get("object_type"),
            )
        elif normalized_type == "template":
            selector_pattern = _derive_selector_pattern(
                "template",
                title,
                description,
                raw_text=template_snippet or str(rule_obj.get("template_snippet") or ""),
            )
        else:
            selector_pattern = _derive_validation_selector_pattern(
                rule_type=normalized_type,
                title=title,
                description=description,
                raw_text=str(raw_text or ""),
                good_example=good_example,
                bad_example=bad_example,
            )
        normalized_rule["selector"] = {"pattern": selector_pattern}
    else:
        normalized_rule["selector"] = selector
    return normalized_rule


def _validate_rule(rule_obj: dict[str, Any]) -> tuple[bool, str | None]:
    rule_type = str(rule_obj.get("type") or "").lower()
    required = ["id", "type", "title", "severity", "description", "confidence"]
    if rule_type not in {"wizard", "template"}:
        required.append("message")
    for key in required:
        if key not in rule_obj:
            return False, f"missing field: {key}"
        if isinstance(rule_obj[key], str) and not rule_obj[key].strip():
            return False, f"empty field: {key}"

    if str(rule_obj.get("type")).lower() not in ALLOWED_RULE_TYPES:
        return False, "invalid type"
    if rule_type == "code":
        subtags = rule_obj.get("subtags")
        if subtags is None:
            return False, "code subtags missing"
        if not isinstance(subtags, list):
            return False, "code subtags must be a list"
        normalized_subtags = _normalize_code_subtags(subtags)
        if not normalized_subtags:
            return False, "code subtags invalid"
    if str(rule_obj.get("severity")).upper() not in ALLOWED_SEVERITIES:
        return False, "invalid severity"

    try:
        confidence = float(rule_obj.get("confidence"))
    except Exception:
        return False, "invalid confidence"
    if confidence < 0 or confidence > 1:
        return False, "confidence out of range"

    selector = rule_obj.get("selector")
    if selector is not None and not isinstance(selector, (str, dict)):
        return False, "invalid selector"
    if rule_type == "template":
        template_block = rule_obj.get("template")
        if not isinstance(template_block, dict):
            return False, "template block missing"
        snippet = str(template_block.get("snippet") or "").strip()
        if not snippet:
            return False, "template snippet missing"
    if rule_type not in {"wizard", "template"}:
        example_block = rule_obj.get("example")
        if not isinstance(example_block, dict):
            return False, "example block missing"
        good_example = str(example_block.get("good") or "").strip()
        if not good_example:
            return False, "example.good missing"
    if str(rule_obj.get("type")).lower() == "wizard":
        wizard_block = rule_obj.get("wizard")
        if not isinstance(wizard_block, dict):
            return False, "wizard block missing"
        step_title = str(wizard_block.get("step_title") or "").strip()
        step_description = str(wizard_block.get("step_description") or "").strip()
        if not step_title:
            return False, "wizard step_title missing"
        if not step_description:
            return False, "wizard step_description missing"
        if not isinstance(wizard_block.get("template"), dict):
            return False, "wizard template missing"
        snippet = str(wizard_block.get("template", {}).get("snippet") or "").strip()
        if not snippet:
            return False, "wizard template snippet missing"
        try:
            step_no = int(wizard_block.get("step_no"))
            if step_no < 1:
                return False, "invalid wizard step_no"
        except Exception:
            return False, "invalid wizard step_no"
    return True, None


def _strip_markdown_fence(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        match = re.search(r"```(?:yaml|yml|json)?\s*([\s\S]*?)```", cleaned, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return cleaned


def _extract_rule_objects(
    yaml_text: str,
    fallback_type: str,
    max_rules: int,
    wizard_name: str | None = None,
    wizard_description: str | None = None,
    wizard_step_title: str | None = None,
    wizard_step_description: str | None = None,
    wizard_step_no: int | None = None,
    wizard_total_steps: int | None = None,
    raw_text: str | None = None,
) -> list[dict[str, Any]]:
    yaml_text = _strip_markdown_fence(yaml_text)
    try:
        loaded = yaml.safe_load(yaml_text)
    except Exception:
        try:
            loaded = json.loads(yaml_text)
        except Exception:
            return []

    candidates: list[dict[str, Any]] = []
    if isinstance(loaded, dict) and isinstance(loaded.get("rules"), list):
        candidates = [item for item in loaded["rules"] if isinstance(item, dict)]
    elif isinstance(loaded, dict) and isinstance(loaded.get("items"), list):
        candidates = [item for item in loaded["items"] if isinstance(item, dict)]
    elif isinstance(loaded, dict) and isinstance(loaded.get("rule"), dict):
        candidates = [loaded["rule"]]
    elif isinstance(loaded, list):
        candidates = [item for item in loaded if isinstance(item, dict)]
    elif isinstance(loaded, dict):
        candidates = [loaded]

    normalized: list[dict[str, Any]] = []
    for idx, item in enumerate(candidates, start=1):
        coerced = _coerce_rule(
            item,
            fallback_type,
            idx,
            wizard_name=wizard_name,
            wizard_description=wizard_description,
            wizard_step_title=wizard_step_title,
            wizard_step_description=wizard_step_description,
            wizard_step_no=wizard_step_no,
            wizard_total_steps=wizard_total_steps,
            raw_text=raw_text,
        )
        valid, _ = _validate_rule(coerced)
        if not valid:
            continue
        normalized.append(coerced)
        if len(normalized) >= max_rules:
            break
    return normalized


def _embedding_text(rule_obj: dict[str, Any], rule_yaml: str) -> str:
    wizard_text = ""
    wizard_block = rule_obj.get("wizard")
    if isinstance(wizard_block, dict):
        template_block = wizard_block.get("template")
        if isinstance(template_block, dict):
            wizard_text = str(template_block.get("snippet") or "")
    return (
        f"{rule_obj.get('title', '')} {rule_obj.get('description', '')} "
        f"{rule_obj.get('selector', '')} {wizard_text} {rule_yaml}"
    )


def _extract_selector_pattern(rule_obj: dict[str, Any]) -> str:
    selector = rule_obj.get("selector")
    if isinstance(selector, dict):
        return str(selector.get("pattern") or "").strip()
    if isinstance(selector, str):
        return selector.strip()
    return ""


def _safe_pattern_match(pattern: str, text: str) -> bool:
    if not pattern or not text:
        return False
    try:
        return re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE) is not None
    except re.error:
        return pattern.lower() in text.lower()


def _code_rule_grounding_score(rule_obj: dict[str, Any], raw_text: str) -> float:
    raw = str(raw_text or "")
    raw_lower = raw.lower()
    selector_pattern = _extract_selector_pattern(rule_obj)
    rule_text = " ".join(
        [
            str(rule_obj.get("title") or ""),
            str(rule_obj.get("description") or ""),
            str(rule_obj.get("message") or ""),
            str(rule_obj.get("fix") or ""),
            str(rule_obj.get("rationale") or ""),
            selector_pattern,
        ]
    ).lower()

    score = 0.0

    # Strong mismatches for over-generalized rules.
    sql_terms = ("select ", "open sql", "for all entries", "join ", "from ")
    if any(term in rule_text for term in sql_terms) and not any(term in raw_lower for term in sql_terms):
        score -= 3.0

    class_terms = ("class ", "constructor", "public section", "private section", "protected section", "interface ")
    if any(term in rule_text for term in class_terms) and not any(term in raw_lower for term in ("class ", "interface ")):
        score -= 3.0

    if selector_pattern:
        score += 2.0 if _safe_pattern_match(selector_pattern, raw) else -1.5

    # Prefer rules grounded to method/function calls found in the snippet.
    call_tokens = re.findall(r"[a-z0-9_]+=>[a-z0-9_]+", raw_lower, flags=re.IGNORECASE)
    if call_tokens:
        if any(token in rule_text for token in call_tokens):
            score += 2.5
        elif "=>" in rule_text:
            score -= 1.0

    token_overlap = len(set(re.findall(r"[a-z0-9_]{3,}", rule_text)) & set(re.findall(r"[a-z0-9_]{3,}", raw_lower)))
    score += min(float(token_overlap) * 0.1, 1.0)
    return score


def _filter_grounded_code_rules(rule_objects: list[dict[str, Any]], raw_text: str) -> list[dict[str, Any]]:
    kept: list[dict[str, Any]] = []
    for rule_obj in rule_objects:
        if str(rule_obj.get("type") or "").lower() != "code":
            kept.append(rule_obj)
            continue
        if _code_rule_grounding_score(rule_obj, raw_text) >= 0.25:
            kept.append(rule_obj)
    return kept


def _detect_singleton_standard(raw_text: str) -> bool:
    up = raw_text.upper()
    signals = 0
    if "CREATE PRIVATE" in up:
        signals += 1
    if "CLASS-DATA" in up and "TYPE REF TO" in up:
        signals += 1
    if "GET_INSTANCE" in up or "GET INSTANCE" in up:
        signals += 1
    if "CONSTRUCTOR" in up and "PRIVATE SECTION" in up:
        signals += 1
    return signals >= 2


def _template_rule_from_code(raw_text: str) -> dict[str, Any]:
    singleton = _detect_singleton_standard(raw_text)
    rule_id = (
        "abap.template.singleton.class"
        if singleton
        else f"abap.template.snippet.{hashlib.sha1(raw_text.encode('utf-8', 'ignore')).hexdigest()[:10]}"
    )
    title = (
        "Use standardized Singleton class template"
        if singleton
        else "Use standardized ABAP template snippet"
    )
    description = (
        "When implementing singleton classes, enforce private constructor, one static instance, and get_instance access method."
        if singleton
        else "Store and reuse this approved ABAP snippet as a coding template."
    )
    selector_pattern = "CREATE PRIVATE + CLASS-DATA ref + get_instance + private constructor" if singleton else "template_snippet"

    return {
        "id": rule_id,
        "type": "template",
        "title": title,
        "severity": "INFO",
        "description": description,
        "selector": {"pattern": selector_pattern},
        "fix": "Reuse the approved template snippet and keep structure consistent.",
        "rationale": "Template-driven standards improve consistency, readability, and maintainability.",
        "confidence": 0.99,
        "template": {
            "language": "ABAP",
            "snippet": raw_text,
        },
    }


async def extract_rules_pipeline(
    raw_text: str,
    rule_type: str = "code",
    max_rules: int = 5,
    wizard_name: str | None = None,
    wizard_description: str | None = None,
    wizard_step_title: str | None = None,
    wizard_step_description: str | None = None,
    wizard_step_no: int | None = None,
    wizard_total_steps: int | None = None,
    template_use_ai: bool = False,
    created_by: str = "anonymous",
) -> list[dict[str, Any]]:
    """
    Generate multiple rule YAML cards using GPT and detect duplicates using Qdrant.
    """

    normalized_rule_type = _normalize_requested_rule_type(rule_type)

    prompt = _build_prompt(
        raw_text,
        rule_type=normalized_rule_type,
        max_rules=max_rules,
        wizard_name=wizard_name,
        wizard_description=wizard_description,
        wizard_step_title=wizard_step_title,
        wizard_step_description=wizard_step_description,
        wizard_step_no=wizard_step_no,
        wizard_total_steps=wizard_total_steps,
    )

    client = _get_openai_client()
    if client is None:
        fallback_yaml = """id: abap.generic.rule
type: code
title: Extraction failed
description: "Model API key is not configured."
message: "Rule extraction failed because no model API key is configured."
confidence: 0.2
"""
        return [
            {
                "yaml": fallback_yaml,
                "confidence": 0.2,
                "duplicate_of": None,
                "similarity": None,
            }
        ]

    try:
        model_name = get_ai_model_name(default="gpt-4o-mini")
        completion = client.responses.create(
            model=model_name,
            input=prompt,
            temperature=0.2,
            max_output_tokens=1600,
        )
        in_tokens, out_tokens, total_tokens = _extract_usage_tokens(getattr(completion, "usage", None))
        if total_tokens > 0:
            log_llm_usage_event(
                developer=created_by,
                feature="rule_extraction_generation",
                provider="openai",
                model=model_name,
                input_tokens=in_tokens,
                output_tokens=out_tokens,
                total_tokens=total_tokens,
                metadata={"rule_type": normalized_rule_type},
            )
        generated_yaml = completion.output_text.strip()
        rule_objects = _extract_rule_objects(
            generated_yaml,
            fallback_type=normalized_rule_type,
            max_rules=max_rules,
            wizard_name=wizard_name,
            wizard_description=wizard_description,
            wizard_step_title=wizard_step_title,
            wizard_step_description=wizard_step_description,
            wizard_step_no=wizard_step_no,
            wizard_total_steps=wizard_total_steps,
            raw_text=raw_text,
        )
        if normalized_rule_type == "code":
            rule_objects = _filter_grounded_code_rules(rule_objects, raw_text=raw_text)

        if not rule_objects:
            if normalized_rule_type in {"wizard", "template"}:
                fallback_yaml = f"""id: rule.{normalized_rule_type}.fallback
type: {normalized_rule_type}
title: Fallback extraction rule
severity: MAJOR
description: LLM returned unparsable output; please refine input and retry.
confidence: 0.3
"""
            else:
                fallback_yaml = f"""id: rule.{normalized_rule_type}.fallback
type: {normalized_rule_type}
title: Fallback extraction rule
severity: MAJOR
description: LLM returned unparsable output; please refine input and retry.
message: "Rule extraction failed: unparsable model output. Refine input and retry."
confidence: 0.3
"""
            return [
                {
                    "yaml": fallback_yaml,
                    "confidence": 0.3,
                    "duplicate_of": None,
                    "similarity": None,
                }
            ]

        results: list[dict[str, Any]] = []
        for idx, rule_obj in enumerate(rule_objects, start=1):
            # Hard-enforce typing/shape for wizard/template extractions.
            if normalized_rule_type in {"wizard", "template"}:
                rule_obj = _coerce_rule(
                    rule_obj,
                    fallback_type=normalized_rule_type,
                    idx=idx,
                    wizard_name=wizard_name,
                    wizard_description=wizard_description,
                    wizard_step_title=wizard_step_title,
                    wizard_step_description=wizard_step_description,
                    wizard_step_no=wizard_step_no,
                    wizard_total_steps=wizard_total_steps,
                    raw_text=raw_text,
                )
            rule_yaml = _safe_rule_yaml(rule_obj)
            if normalized_rule_type == "template":
                rule_yaml = _ensure_template_snippet_yaml(rule_yaml, raw_text)
            embedding_response = client.embeddings.create(
                model="text-embedding-3-small",
                input=_embedding_text(rule_obj, rule_yaml),
            )
            embedding = embedding_response.data[0].embedding
            emb_in, emb_out, emb_total = _extract_usage_tokens(getattr(embedding_response, "usage", None))
            if emb_total > 0:
                log_llm_usage_event(
                    developer=created_by,
                    feature="rule_extraction_embedding",
                    provider="openai",
                    model="text-embedding-3-small",
                    input_tokens=emb_in if emb_in > 0 else emb_total,
                    output_tokens=emb_out,
                    total_tokens=emb_total,
                    metadata={"rule_type": normalized_rule_type},
                )
            duplicate_id, similarity = find_duplicate_rule(embedding, threshold=0.88)
            new_id = str(rule_obj.get("id") or f"rule.{abs(hash(rule_yaml)) % (10**10)}")
            upsert_rule_vector(
                rule_id=new_id,
                vector=embedding,
                yaml_text=rule_yaml,
                metadata={"rule_type": normalized_rule_type},
            )

            confidence = 0.7
            try:
                confidence = float(rule_obj.get("confidence", 0.7))
            except Exception:
                confidence = 0.7

            results.append(
                {
                    "yaml": rule_yaml,
                    "confidence": max(0.0, min(1.0, confidence)),
                    "duplicate_of": duplicate_id,
                    "similarity": similarity,
                }
            )

        return results

    except Exception as e:
        fallback_yaml = f"""id: abap.generic.rule
type: code
title: Extraction failed
description: "{str(e)}"
message: "Rule extraction failed due to internal processing error."
confidence: 0.2
"""
        return [
            {
                "yaml": fallback_yaml,
                "confidence": 0.2,
                "duplicate_of": None,
                "similarity": None,
            }
        ]


def _normalize_rule_types(rule_types: list[str] | None = None) -> list[str]:
    if not rule_types:
        return ["code"]
    normalized: list[str] = []
    for item in rule_types:
        t = _normalize_requested_rule_type(item)
        if t and t not in normalized:
            normalized.append(t)
    return normalized or ["code"]


async def extract_rules_multi_pipeline(
    raw_text: str,
    rule_types: list[str],
    max_rules: int = 5,
    wizard_name: str | None = None,
    wizard_description: str | None = None,
    wizard_step_title: str | None = None,
    wizard_step_description: str | None = None,
    wizard_step_no: int | None = None,
    wizard_total_steps: int | None = None,
    template_use_ai: bool = False,
    created_by: str = "anonymous",
) -> list[dict[str, Any]]:
    selected_types = _normalize_rule_types(rule_types)
    safe_max = max(1, min(int(max_rules or 1), 10))

    if len(selected_types) == 1:
        return await extract_rules_pipeline(
            raw_text=raw_text,
            rule_type=selected_types[0],
            max_rules=safe_max,
            wizard_name=wizard_name,
            wizard_description=wizard_description,
            wizard_step_title=wizard_step_title,
            wizard_step_description=wizard_step_description,
            wizard_step_no=wizard_step_no,
            wizard_total_steps=wizard_total_steps,
            template_use_ai=template_use_ai,
            created_by=created_by,
        )

    # Keep total extracted rules within requested max.
    if safe_max < len(selected_types):
        selected_types = selected_types[:safe_max]
    per_type = max(1, safe_max // len(selected_types))
    remainder = safe_max - (per_type * len(selected_types))

    merged: list[dict[str, Any]] = []
    for idx, current_type in enumerate(selected_types):
        type_max = per_type + (1 if idx < remainder else 0)
        extracted = await extract_rules_pipeline(
            raw_text=raw_text,
            rule_type=current_type,
            max_rules=type_max,
            wizard_name=wizard_name if current_type == "wizard" else None,
            wizard_description=wizard_description if current_type == "wizard" else None,
            wizard_step_title=wizard_step_title if current_type == "wizard" else None,
            wizard_step_description=wizard_step_description if current_type == "wizard" else None,
            wizard_step_no=wizard_step_no if current_type == "wizard" else None,
            wizard_total_steps=wizard_total_steps if current_type == "wizard" else None,
            template_use_ai=template_use_ai if current_type == "template" else False,
            created_by=created_by,
        )
        merged.extend(extracted)

    return merged[:safe_max]


async def extract_rule_pipeline(raw_text: str, rule_type: str = "code") -> dict[str, Any]:
    """
    Backward-compatible single-rule wrapper.
    """
    rules = await extract_rules_pipeline(raw_text, rule_type=rule_type, max_rules=1)
    return rules[0]
