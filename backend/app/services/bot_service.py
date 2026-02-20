from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

from app.services.store_service import (
    create_dashboard_violation,
    get_model_api_key,
    get_rules_for_pack,
    get_rules_for_project,
    list_rule_packs,
)
from app.services.vector_store_service import search_rule_vectors

BASE_DIR = Path(__file__).resolve().parents[2]
load_dotenv(dotenv_path=BASE_DIR / ".env", override=True)


@dataclass
class ResolvedRule:
    rule_id: str
    rule_type: str
    title: str
    description: str
    message: str
    severity: str
    selector_pattern: str
    fix: str
    rationale: str
    rule_pack: str
    template_snippet: str
    wizard_snippet: str
    metadata: dict[str, Any]
    raw_yaml: str


_EMBED_CLIENT = None
_EMBED_CLIENT_KEY = ""


def _get_embed_client():
    global _EMBED_CLIENT, _EMBED_CLIENT_KEY
    api_key = get_model_api_key()
    if not api_key:
        _EMBED_CLIENT = None
        _EMBED_CLIENT_KEY = ""
        return None
    if _EMBED_CLIENT is not None and _EMBED_CLIENT_KEY == api_key:
        return _EMBED_CLIENT
    try:
        from openai import OpenAI  # lazy import

        _EMBED_CLIENT = OpenAI(api_key=api_key)
        _EMBED_CLIENT_KEY = api_key
        return _EMBED_CLIENT
    except Exception:
        _EMBED_CLIENT = None
        _EMBED_CLIENT_KEY = ""
        return None


def _tokenize(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9_]{3,}", text.lower())}


def _line_from_index(text: str, index: int) -> int:
    if index <= 0:
        return 1
    return text.count("\n", 0, index) + 1


def _safe_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _rule_requires_arithmetic_try_catch(rule: ResolvedRule) -> bool:
    haystack = " ".join(
        [
            rule.title,
            rule.description,
            rule.message,
            rule.fix,
            rule.rationale,
            rule.selector_pattern,
            rule.raw_yaml,
        ]
    ).lower()
    has_try_catch = ("try" in haystack and "catch" in haystack) or "endtry" in haystack
    if not has_try_catch:
        return False
    arithmetic_keywords = (
        "arith",
        "overflow",
        "calculation",
        "numeric",
        "division",
        "multiply",
        "addition",
        "subtraction",
    )
    if any(keyword in haystack for keyword in arithmetic_keywords):
        return True
    return bool(re.search(r"[a-z0-9_]\s*=\s*[^\n.]*[+\-*/][^\n.]*\.", haystack, flags=re.IGNORECASE))


def _rule_requires_try_catch(rule: ResolvedRule) -> bool:
    haystack = " ".join(
        [
            rule.title,
            rule.description,
            rule.message,
            rule.fix,
            rule.rationale,
            rule.selector_pattern,
            rule.raw_yaml,
        ]
    ).lower()
    return ("try" in haystack and "catch" in haystack) or "endtry" in haystack


def _code_has_try_catch_block(code: str) -> bool:
    up = code.upper()
    return "TRY." in up and "CATCH" in up and "ENDTRY." in up


def _strip_abap_inline_comment(line: str) -> str:
    trimmed = line.lstrip()
    if trimmed.startswith("*"):
        return ""
    if '"' in line:
        return line.split('"', 1)[0]
    return line


def _find_unprotected_arithmetic_operation(code: str) -> tuple[int, str] | None:
    try_depth = 0
    for idx, raw_line in enumerate(code.splitlines(), start=1):
        line = _strip_abap_inline_comment(raw_line)
        if not line.strip():
            continue
        upper_line = line.upper()
        if "TRY." in upper_line:
            try_depth += upper_line.count("TRY.")
        if re.search(r"\b[A-Z0-9_]+\b\s*=\s*[^.\n]*[+\-*/][^.\n]*\.", line, flags=re.IGNORECASE):
            if try_depth <= 0:
                return idx, raw_line.strip()
        if "ENDTRY." in upper_line:
            try_depth = max(0, try_depth - upper_line.count("ENDTRY."))
    return None


def _resolve_rule(rule_row: dict[str, Any]) -> ResolvedRule | None:
    yaml_text = str(rule_row.get("yaml") or "").strip()
    if not yaml_text:
        return None

    try:
        parsed = yaml.safe_load(yaml_text)
    except Exception:
        parsed = {}
    if not isinstance(parsed, dict):
        parsed = {}

    selector = parsed.get("selector")
    selector_pattern = ""
    if isinstance(selector, dict):
        selector_pattern = str(selector.get("pattern") or "").strip()
    elif isinstance(selector, str):
        selector_pattern = selector.strip()

    template_block = _safe_dict(parsed.get("template"))
    wizard_block = _safe_dict(parsed.get("wizard"))
    wizard_template = _safe_dict(wizard_block.get("template"))

    rule_id = str(
        parsed.get("id")
        or rule_row.get("_id")
        or "unknown.rule"
    ).strip()
    rule_type = str(
        parsed.get("type")
        or rule_row.get("category")
        or "code"
    ).lower().strip()
    severity = str(
        parsed.get("severity")
        or rule_row.get("_severity")
        or "MAJOR"
    ).upper().strip()

    return ResolvedRule(
        rule_id=rule_id,
        rule_type=rule_type,
        title=str(parsed.get("title") or rule_id).strip(),
        description=str(parsed.get("description") or "").strip(),
        message=str(parsed.get("message") or parsed.get("description") or rule_id).strip(),
        severity=severity or "MAJOR",
        selector_pattern=selector_pattern,
        fix=str(parsed.get("fix") or "").strip(),
        rationale=str(parsed.get("rationale") or "").strip(),
        rule_pack=str(rule_row.get("rule_pack") or "generic").strip() or "generic",
        template_snippet=str(template_block.get("snippet") or "").strip(),
        wizard_snippet=str(wizard_template.get("snippet") or "").strip(),
        metadata=_safe_dict(parsed.get("metadata")),
        raw_yaml=yaml_text,
    )


def _load_rule_rows(
    project_id: str | None,
    pack_name: str | None,
    created_by: str | None,
) -> list[dict[str, Any]]:
    if pack_name:
        rows = get_rules_for_pack(pack_name, project_id=project_id, created_by=created_by)
        if rows:
            return rows
        # Pack rules are shared governance assets; allow cross-user fallback.
        return get_rules_for_pack(pack_name, project_id=project_id, created_by=None)
    if project_id:
        return get_rules_for_project(project_id, created_by=created_by)

    rows: list[dict[str, Any]] = []
    for pack in list_rule_packs(created_by=created_by)[:8]:
        name = str(pack.get("name") or "").strip()
        if not name:
            continue
        rows.extend(get_rules_for_pack(name, created_by=created_by))
    if rows:
        return rows

    # Fallback to shared/global pack rules when user-scoped discovery finds none.
    for pack in list_rule_packs(created_by=None)[:8]:
        name = str(pack.get("name") or "").strip()
        if not name:
            continue
        rows.extend(get_rules_for_pack(name, created_by=None))
    return rows


def _rank_rules(query: str, rules: list[ResolvedRule]) -> list[ResolvedRule]:
    query_tokens = _tokenize(query)
    if not query_tokens:
        return rules[:]

    scored: list[tuple[float, ResolvedRule]] = []
    for rule in rules:
        haystack = " ".join(
            [
                rule.title,
                rule.description,
                rule.message,
                rule.selector_pattern,
                rule.fix,
                rule.rationale,
                rule.template_snippet,
                rule.wizard_snippet,
                rule.rule_id,
                rule.rule_type,
            ]
        )
        tokens = _tokenize(haystack)
        overlap = len(query_tokens & tokens)
        score = float(overlap)
        if query.lower() in haystack.lower():
            score += 2.0
        if rule.rule_type in {"template", "wizard"} and (
            "template" in query.lower() or "wizard" in query.lower()
        ):
            score += 2.0
        if score > 0:
            scored.append((score, rule))

    if not scored:
        return rules[:]

    scored.sort(key=lambda item: item[0], reverse=True)
    return [item[1] for item in scored]


def _vector_rank(query: str, rules: list[ResolvedRule]) -> list[ResolvedRule]:
    client = _get_embed_client()
    if client is None:
        return []
    try:
        vector = client.embeddings.create(
            model="text-embedding-3-small",
            input=query,
        ).data[0].embedding
        hits = search_rule_vectors(vector, limit=10)
    except Exception:
        return []

    by_id = {rule.rule_id: rule for rule in rules}
    ranked: list[ResolvedRule] = []
    seen: set[str] = set()
    for hit in hits:
        rid = str(hit.get("id") or "").strip()
        if not rid or rid in seen:
            continue
        rule = by_id.get(rid)
        if rule:
            ranked.append(rule)
            seen.add(rid)
    return ranked


def _validate_code(code: str, rules: list[ResolvedRule]) -> list[dict[str, Any]]:
    violations: list[dict[str, Any]] = []
    if not code.strip():
        return violations

    valid_types = {"code", "design", "naming", "performance"}
    for rule in rules:
        if rule.rule_type not in valid_types:
            continue

        if _rule_requires_try_catch(rule) and not _rule_requires_arithmetic_try_catch(rule):
            if not _code_has_try_catch_block(code):
                violations.append(
                    {
                        "rule_id": rule.rule_id,
                        "title": rule.title,
                        "message": rule.message or "Required TRY...CATCH block is missing.",
                        "severity": rule.severity,
                        "line": 1,
                        "rule_pack": rule.rule_pack,
                        "description": rule.description,
                        "fix": rule.fix or "Wrap exception-prone logic in TRY...CATCH...ENDTRY.",
                        "rationale": rule.rationale,
                        "suggested_code": (
                            rule.template_snippet
                            or rule.wizard_snippet
                            or "TRY.\n  \" code\nCATCH cx_root INTO DATA(lx_error).\nENDTRY."
                        ),
                    }
                )
            continue

        if _rule_requires_arithmetic_try_catch(rule):
            unprotected = _find_unprotected_arithmetic_operation(code)
            if unprotected is not None:
                line_no, line_text = unprotected
                violations.append(
                    {
                        "rule_id": rule.rule_id,
                        "title": rule.title,
                        "message": rule.message or "Arithmetic operation must be inside TRY...CATCH.",
                        "severity": rule.severity,
                        "line": line_no,
                        "rule_pack": rule.rule_pack,
                        "description": rule.description,
                        "fix": rule.fix or "Wrap arithmetic operations in TRY...CATCH...ENDTRY.",
                        "rationale": rule.rationale,
                        "suggested_code": (
                            rule.template_snippet
                            or rule.wizard_snippet
                            or f"TRY.\n  {line_text}\nCATCH cx_sy_arithmetic_overflow.\nENDTRY."
                        ),
                    }
                )
            continue
        if not rule.selector_pattern:
            continue

        match = None
        try:
            match = re.search(rule.selector_pattern, code, flags=re.IGNORECASE | re.MULTILINE)
        except re.error:
            idx = code.lower().find(rule.selector_pattern.lower())
            if idx >= 0:
                class _Dummy:
                    def __init__(self, pos: int):
                        self._pos = pos

                    def start(self) -> int:
                        return self._pos

                match = _Dummy(idx)

        if match is None:
            continue

        start = match.start() if hasattr(match, "start") else 0
        violations.append(
            {
                "rule_id": rule.rule_id,
                "title": rule.title,
                "message": rule.message,
                "severity": rule.severity,
                "line": _line_from_index(code, start),
                "rule_pack": rule.rule_pack,
                "description": rule.description,
                "fix": rule.fix,
                "rationale": rule.rationale,
                "suggested_code": rule.template_snippet or rule.wizard_snippet,
            }
        )
    return violations


def _build_suggestions(rules: list[ResolvedRule], top_k: int) -> dict[str, list[dict[str, str]]]:
    templates: list[dict[str, str]] = []
    wizards: list[dict[str, str]] = []
    for rule in rules:
        if rule.rule_type == "template" and rule.template_snippet:
            templates.append(
                {
                    "rule_id": rule.rule_id,
                    "title": rule.title,
                    "snippet": rule.template_snippet,
                    "rule_pack": rule.rule_pack,
                }
            )
        if rule.rule_type == "wizard" and rule.wizard_snippet:
            wizards.append(
                {
                    "rule_id": rule.rule_id,
                    "title": rule.title,
                    "snippet": rule.wizard_snippet,
                    "rule_pack": rule.rule_pack,
                }
            )
        if len(templates) >= top_k and len(wizards) >= top_k:
            break

    return {
        "templates": templates[:top_k],
        "wizards": wizards[:top_k],
    }


def _extract_query_intent(query: str) -> dict[str, bool]:
    q = (query or "").lower()
    return {
        "wants_country": any(term in q for term in ("country", "molga", "land1", "nationality")),
        "wants_manager_scope": any(term in q for term in ("manager", "reportee", "teamviewer", "mss")),
        "wants_employee": any(term in q for term in ("employee", "pernr", "personnel", "emp")),
    }


def _template_intent_score(query: str, rule: ResolvedRule) -> float:
    intent = _extract_query_intent(query)
    haystack = " ".join(
        [
            rule.title,
            rule.description,
            rule.selector_pattern,
            rule.template_snippet,
            rule.raw_yaml,
            " ".join([str(k) for k in rule.metadata.keys()]),
            " ".join([str(v) for v in rule.metadata.values()]),
        ]
    ).lower()
    q_tokens = _tokenize(query)
    h_tokens = _tokenize(haystack)
    score = float(len(q_tokens & h_tokens))

    if intent["wants_employee"] and "employee" in haystack:
        score += 1.5

    if intent["wants_country"]:
        if any(term in haystack for term in ("country", "molga", "land1", "nationality")):
            score += 6.0
        if any(term in haystack for term in ("manager", "reportee", "teamviewer", "mss")):
            score -= 3.0

    if intent["wants_manager_scope"]:
        if any(term in haystack for term in ("manager", "reportee", "teamviewer", "mss")):
            score += 5.0
        if any(term in haystack for term in ("country", "molga", "land1", "nationality")):
            score -= 1.0

    return score


def _build_suggestions_for_query(query: str, rules: list[ResolvedRule], top_k: int) -> dict[str, list[dict[str, str]]]:
    template_rules = [r for r in rules if r.rule_type == "template" and r.template_snippet]
    wizard_rules = [r for r in rules if r.rule_type == "wizard" and r.wizard_snippet]

    ranked_templates = sorted(
        template_rules,
        key=lambda rule: _template_intent_score(query, rule),
        reverse=True,
    )

    ranked_rules: list[ResolvedRule] = []
    ranked_rules.extend(ranked_templates)
    ranked_rules.extend(wizard_rules)
    return _build_suggestions(ranked_rules, top_k=top_k)


def _is_validation_query(query: str) -> bool:
    q = (query or "").lower()
    return "validate" in q or "violation" in q or "check code" in q


def _is_template_or_wizard_request(query: str) -> bool:
    q = (query or "").lower()
    template_terms = (
        "template",
        "snippet",
        "boilerplate",
        "scaffold",
        "generate class",
        "wizard",
        "step by step",
    )
    if any(term in q for term in template_terms):
        return True

    code_generation_phrases = (
        "give code",
        "provide code",
        "sample code",
        "example code",
        "code for",
        "how to implement",
        "generate code",
        "show code",
        "need code",
        "help with code",
    )
    if any(phrase in q for phrase in code_generation_phrases):
        return True

    has_code_word = bool(re.search(r"\b(code|example|implementation|logic)\b", q))
    has_action_word = bool(re.search(r"\b(get|fetch|retrieve|create|build|implement|generate)\b", q))
    has_domain_hint = bool(re.search(r"\b(employee|employees|manager|manger|reportee|team|role)\b", q))
    return has_code_word and (has_action_word or has_domain_hint)


def _log_violations_to_dashboard(
    violations: list[dict[str, Any]],
    object_name: str,
    transport: str,
    developer: str,
) -> int:
    count = 0
    for violation in violations:
        try:
            create_dashboard_violation(
                rule_pack=str(violation.get("rule_pack") or "generic"),
                object_name=object_name,
                transport=transport,
                developer=developer,
                severity=str(violation.get("severity") or "MAJOR"),
            )
            count += 1
        except Exception:
            continue
    return count


def assist_with_rules(
    query: str,
    code: str = "",
    object_name: str = "ADT_OBJECT",
    project_id: str | None = None,
    pack_name: str | None = None,
    developer: str = "name@zalaris.com",
    transport: str = "ADT",
    created_by: str | None = None,
    top_k: int = 5,
    log_violations: bool = True,
) -> dict[str, Any]:
    rule_rows = _load_rule_rows(project_id=project_id, pack_name=pack_name, created_by=created_by)
    resolved = [rule for row in rule_rows if (rule := _resolve_rule(row)) is not None]

    lex_ranked = _rank_rules(query, resolved)
    vec_ranked = _vector_rank(query, resolved)

    merged: list[ResolvedRule] = []
    seen_ids: set[str] = set()
    for bucket in (vec_ranked, lex_ranked):
        for rule in bucket:
            if rule.rule_id in seen_ids:
                continue
            merged.append(rule)
            seen_ids.add(rule.rule_id)
    if not merged:
        merged = resolved[:]

    retrieved = merged[: max(1, min(top_k, 10))]
    is_validate = _is_validation_query(query)
    violations = _validate_code(code, resolved) if is_validate else []
    logged = 0
    if log_violations and violations:
        logged = _log_violations_to_dashboard(
            violations=violations,
            object_name=object_name,
            transport=transport,
            developer=developer,
        )

    wants_template = _is_template_or_wizard_request(query)
    if wants_template:
        template_pool = [r for r in merged if r.rule_type in {"template", "wizard"}]
        if not template_pool:
            template_pool = [r for r in resolved if r.rule_type in {"template", "wizard"}]
        suggestions = _build_suggestions_for_query(query, template_pool, top_k=min(3, top_k))
    else:
        suggestions = {"templates": [], "wizards": []}
    if violations:
        message = f"Validation failed: {len(violations)} violation(s) found."
    elif is_validate:
        message = "Validation passed: no violations found."
    elif suggestions["templates"] or suggestions["wizards"]:
        message = "Found relevant templates/wizard steps from your saved governance rules."
    elif wants_template:
        message = "No matching templates/wizards found. Save a template and retry with a similar intent."
    elif retrieved:
        message = "Retrieved relevant governance rules."
    else:
        message = "No matching rules found. Create rules/packs in dashboard and retry."

    return {
        "message": message,
        "violations": violations,
        "violations_logged": logged,
        "suggestions": suggestions,
        "retrieved": [
            {
                "rule_id": rule.rule_id,
                "type": rule.rule_type,
                "title": rule.title,
                "severity": rule.severity,
                "rule_pack": rule.rule_pack,
                "description": rule.description,
                "selector_pattern": rule.selector_pattern,
            }
            for rule in retrieved
        ],
    }
