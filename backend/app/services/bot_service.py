from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

from app.services.store_service import (
    add_wizard_session_event,
    create_dashboard_violation,
    get_active_wizard_session,
    log_llm_usage_event,
    get_ai_llm_fallback_enabled,
    get_ai_model_name,
    get_model_api_key,
    get_rules_for_pack,
    get_rules_for_project,
    get_wizard_session,
    get_wizard_steps,
    list_rule_packs,
    list_wizard_session_events,
    list_wizards,
    start_wizard_session,
    update_wizard_session,
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
    subtags: list[str]
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


def _extract_usage_tokens(usage: Any) -> tuple[int, int, int]:
    if usage is None:
        return 0, 0, 0
    prompt = 0
    completion = 0
    total = 0
    if isinstance(usage, dict):
        prompt = int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
        completion = int(usage.get("completion_tokens") or usage.get("output_tokens") or 0)
        total = int(usage.get("total_tokens") or 0)
    else:
        prompt = int(getattr(usage, "prompt_tokens", 0) or getattr(usage, "input_tokens", 0) or 0)
        completion = int(getattr(usage, "completion_tokens", 0) or getattr(usage, "output_tokens", 0) or 0)
        total = int(getattr(usage, "total_tokens", 0) or 0)
    if total <= 0:
        total = max(0, prompt) + max(0, completion)
    return max(0, prompt), max(0, completion), max(0, total)


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
        if item in {"code", "naming", "performance"} and item not in out:
            out.append(item)
    return out


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
    raw_rule_type = str(
        parsed.get("type")
        or rule_row.get("category")
        or "code"
    ).lower().strip()
    rule_type = raw_rule_type
    severity = str(
        parsed.get("severity")
        or rule_row.get("_severity")
        or "MAJOR"
    ).upper().strip()
    subtags = _normalize_code_subtags(parsed.get("subtags"))
    metadata = _safe_dict(parsed.get("metadata"))
    if raw_rule_type in {"naming", "performance"}:
        rule_type = "code"
        if "code" not in subtags:
            subtags.insert(0, "code")
        if raw_rule_type not in subtags:
            subtags.append(raw_rule_type)
        metadata["legacy_type"] = raw_rule_type
    elif rule_type == "code" and "code" not in subtags:
        subtags.insert(0, "code")

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
        subtags=subtags,
        metadata=metadata,
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


def _vector_scores(query: str, rules: list[ResolvedRule], developer: str) -> dict[str, float]:
    client = _get_embed_client()
    if client is None:
        return {}
    try:
        embed_response = client.embeddings.create(
            model="text-embedding-3-small",
            input=query,
        )
        vector = embed_response.data[0].embedding
        hits = search_rule_vectors(vector, limit=25)
        in_tokens, out_tokens, total_tokens = _extract_usage_tokens(getattr(embed_response, "usage", None))
        if total_tokens > 0:
            log_llm_usage_event(
                developer=developer,
                feature="rule_retrieval_embedding",
                provider="openai",
                model="text-embedding-3-small",
                input_tokens=in_tokens if in_tokens > 0 else total_tokens,
                output_tokens=out_tokens,
                total_tokens=total_tokens,
                metadata={"query_length": len(query or "")},
            )
    except Exception:
        return {}

    by_id = {rule.rule_id: rule for rule in rules}
    scores: dict[str, float] = {}
    for hit in hits:
        rid = str(hit.get("id") or "").strip()
        if not rid:
            continue
        if rid in by_id:
            scores[rid] = max(scores.get(rid, 0.0), float(hit.get("score") or 0.0))
    return scores


def _validate_code(code: str, rules: list[ResolvedRule]) -> list[dict[str, Any]]:
    violations: list[dict[str, Any]] = []
    if not code.strip():
        return violations

    valid_types = {"code", "design"}
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
        "wants_factory_pattern": bool(re.search(r"\bfactory(\s+pattern)?\b", q)),
        "wants_singleton_pattern": bool(re.search(r"\bsingleton(\s+pattern)?\b", q)),
        "wants_strategy_pattern": bool(re.search(r"\bstrategy(\s+pattern)?\b", q)),
        "wants_builder_pattern": bool(re.search(r"\bbuilder(\s+pattern)?\b", q)),
    }


def _query_has_design_pattern_intent(intent: dict[str, bool]) -> bool:
    return any(
        [
            intent["wants_factory_pattern"],
            intent["wants_singleton_pattern"],
            intent["wants_strategy_pattern"],
            intent["wants_builder_pattern"],
        ]
    )


def _rule_haystack(rule: ResolvedRule) -> str:
    return " ".join(
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
            " ".join([str(v) for v in rule.metadata.values()]),
        ]
    ).lower()


def _compute_rule_relevance(
    query: str,
    intent: dict[str, bool],
    rule: ResolvedRule,
    vector_score: float = 0.0,
) -> float:
    haystack = _rule_haystack(rule)
    query_text = (query or "").strip().lower()
    query_tokens = _tokenize(query_text)
    if not query_tokens:
        return 0.0

    overlap = len(query_tokens & _tokenize(haystack))
    score = float(overlap)
    if query_text and query_text in haystack:
        score += 2.5

    # Blend lexical and vector semantic signal.
    score += max(0.0, min(1.0, vector_score)) * 3.0

    # Template/wizard prompts should prefer template/wizard assets.
    if _is_template_or_wizard_request(query_text):
        if rule.rule_type in {"template", "wizard"}:
            score += 1.5
        else:
            score -= 1.5

    # Penalize domain templates when asking design patterns.
    if _query_has_design_pattern_intent(intent):
        domain_noise = ("employee", "pernr", "molga", "reportee", "manager", "country")
        if any(term in haystack for term in domain_noise):
            score -= 4.0

    pattern_expectations = [
        (intent["wants_factory_pattern"], ("factory", "creator", "create object", "instantiate")),
        (intent["wants_singleton_pattern"], ("singleton", "get_instance", "create private")),
        (intent["wants_strategy_pattern"], ("strategy", "interface", "polymorph")),
        (intent["wants_builder_pattern"], ("builder", "director", "build")),
    ]
    for requested, hints in pattern_expectations:
        if not requested:
            continue
        if any(h in haystack for h in hints):
            score += 7.0
        else:
            score -= 7.0

    if intent["wants_country"]:
        if any(term in haystack for term in ("country", "molga", "land1", "nationality")):
            score += 5.0
        if any(term in haystack for term in ("manager", "reportee", "teamviewer", "mss")):
            score -= 3.0

    if intent["wants_manager_scope"]:
        if any(term in haystack for term in ("manager", "reportee", "teamviewer", "mss")):
            score += 5.0
        if any(term in haystack for term in ("country", "molga", "land1", "nationality")):
            score -= 2.0

    if intent["wants_employee"] and "employee" in haystack:
        score += 1.0

    return score


def _min_relevance_threshold(query: str, intent: dict[str, bool], is_validate: bool) -> float:
    if is_validate:
        return 0.5
    if _query_has_design_pattern_intent(intent):
        return 4.0
    if _is_template_or_wizard_request(query):
        return 2.0
    return 1.5


def _filter_candidate_pool(query: str, rules: list[ResolvedRule], is_validate: bool) -> list[ResolvedRule]:
    if is_validate:
        return [r for r in rules if r.rule_type in {"code", "design"}]
    if _is_template_or_wizard_request(query):
        return [r for r in rules if r.rule_type in {"template", "wizard"}]
    return [r for r in rules if r.rule_type in {"code", "design", "template", "wizard"}]


def _rank_rules(
    query: str,
    rules: list[ResolvedRule],
    is_validate: bool,
    developer: str,
) -> tuple[list[ResolvedRule], dict[str, float]]:
    if not rules:
        return [], {}
    intent = _extract_query_intent(query)
    threshold = _min_relevance_threshold(query, intent, is_validate)
    candidate_pool = _filter_candidate_pool(query, rules, is_validate)
    vector_map = _vector_scores(query, candidate_pool, developer=developer)

    scored: list[tuple[float, ResolvedRule]] = []
    for rule in candidate_pool:
        score = _compute_rule_relevance(query, intent, rule, vector_map.get(rule.rule_id, 0.0))
        if score >= threshold:
            scored.append((score, rule))

    scored.sort(key=lambda item: item[0], reverse=True)
    ranked = [item[1] for item in scored]
    score_map = {rule.rule_id: score for score, rule in scored}
    return ranked, score_map


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
    return _compute_rule_relevance(query, intent, rule, vector_score=0.0)


def _build_suggestions_for_query(query: str, rules: list[ResolvedRule], top_k: int) -> dict[str, list[dict[str, str]]]:
    template_rules = [r for r in rules if r.rule_type == "template" and r.template_snippet]
    wizard_rules = [r for r in rules if r.rule_type == "wizard" and r.wizard_snippet]
    scored_templates = sorted(
        [(_template_intent_score(query, rule), rule) for rule in template_rules],
        key=lambda item: item[0],
        reverse=True,
    )
    intent = _extract_query_intent(query)
    is_design_pattern_request = _query_has_design_pattern_intent(intent)
    min_score = 3.0 if is_design_pattern_request else 1.5
    ranked_templates = [rule for score, rule in scored_templates if score >= min_score]

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


def _has_satisfactory_rule_match(query: str, rules: list[ResolvedRule]) -> bool:
    intent = _extract_query_intent(query)
    threshold = _min_relevance_threshold(query, intent, is_validate=False)
    if not (query or "").strip():
        return False

    for rule in rules:
        if _compute_rule_relevance(query, intent, rule, 0.0) >= threshold:
            return True
    return False


def _generate_llm_fallback_answer(
    query: str,
    code: str,
    retrieved: list[ResolvedRule],
    suggestions: dict[str, list[dict[str, str]]],
    top_k: int,
    developer: str,
) -> str | None:
    client = _get_embed_client()
    if client is None:
        return None

    context_blocks: list[str] = []
    for rule in retrieved[: max(1, min(top_k, 5))]:
        context_blocks.append(
            "\n".join(
                [
                    f"Rule: {rule.title}",
                    f"Type: {rule.rule_type}",
                    f"Severity: {rule.severity}",
                    f"Description: {rule.description}",
                    f"Fix: {rule.fix}",
                ]
            )
        )
    for item in suggestions.get("templates", [])[:2]:
        context_blocks.append(
            "\n".join(
                [
                    f"Template: {item.get('title', '')}",
                    f"Snippet:\n{item.get('snippet', '')}",
                ]
            )
        )

    context_text = "\n\n".join(context_blocks).strip()
    model = get_ai_model_name(default="gpt-4.1-mini")

    messages = [
        {
            "role": "system",
            "content": (
                "You are an ABAP governance assistant. Give safe, practical, concise guidance. "
                "If uncertain, say assumptions clearly. Prefer standards-compliant ABAP patterns."
            ),
        },
        {
            "role": "user",
            "content": "\n\n".join(
                [
                    f"Developer request:\n{query}",
                    f"ABAP code context (may be empty):\n{code or '(none)'}",
                    f"Governance context:\n{context_text or '(no direct rule matches)'}",
                    "Provide: 1) what to do, 2) why, 3) an ABAP example/template when relevant.",
                ]
            ),
        },
    ]

    try:
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.2,
            max_tokens=700,
        )
        in_tokens, out_tokens, total_tokens = _extract_usage_tokens(getattr(response, "usage", None))
        if total_tokens > 0:
            log_llm_usage_event(
                developer=developer,
                feature="llm_fallback_chat",
                provider="openai",
                model=model,
                input_tokens=in_tokens,
                output_tokens=out_tokens,
                total_tokens=total_tokens,
                metadata={"context_rules": len(retrieved), "context_templates": len(suggestions.get("templates", []))},
            )
        content = response.choices[0].message.content if response.choices else ""
        return (content or "").strip() or None
    except Exception:
        return None


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
                transport=transport or "",
                developer=developer,
                severity=str(violation.get("severity") or "MAJOR"),
            )
            count += 1
        except Exception:
            continue
    return count


def _wizard_step_card(step: dict[str, Any], total_steps: int) -> str:
    step_no = int(step.get("step_no") or 1)
    title = str(step.get("title") or f"Step {step_no}").strip()
    description = str(step.get("description") or "").strip()
    snippet = str(step.get("snippet") or "").strip()
    object_type = str(step.get("object_type") or "").strip()
    depends = step.get("depends_on") if isinstance(step.get("depends_on"), list) else []

    lines: list[str] = [f"Step {step_no}/{max(1, int(total_steps or 1))}: {title}"]
    if object_type:
        lines.append(f"Object type: {object_type}")
    if description:
        lines.append(f"What to do: {description}")
    if depends:
        lines.append(f"Depends on steps: {', '.join(str(x) for x in depends)}")
    if snippet:
        lines.append("Suggested ABAP snippet:")
        lines.append(snippet)
    lines.append("Reply 'done' after activation to continue to the next step.")
    return "\n".join(lines)


def _is_done_signal(query: str) -> bool:
    q = (query or "").strip().lower()
    if q in {"done", "completed", "next", "continue", "ok done", "done.", "activated"}:
        return True
    return bool(re.search(r"\b(done|completed|activated|next step|proceed)\b", q))


def _is_status_signal(query: str) -> bool:
    q = (query or "").strip().lower()
    return bool(re.search(r"\b(status|progress|where are we|current step|what next)\b", q))


def _wizard_candidate_score(query: str, wizard: dict[str, Any]) -> float:
    q_tokens = _tokenize(query or "")
    haystack = " ".join(
        [
            str(wizard.get("name") or ""),
            str(wizard.get("description") or ""),
            str(wizard.get("rule_pack") or ""),
        ]
    ).lower()
    h_tokens = _tokenize(haystack)
    score = float(len(q_tokens & h_tokens))
    if str(wizard.get("name") or "").lower() in (query or "").lower():
        score += 3.0
    if "rap" in (query or "").lower() and "rap" in haystack:
        score += 4.0
    if "wizard" in (query or "").lower():
        score += 1.0
    return score


def _find_best_wizard_for_query(
    query: str,
    created_by: str | None,
    project_id: str | None,
) -> dict[str, Any] | None:
    own = list_wizards(created_by=created_by, project_id=project_id, q=None)
    shared = list_wizards(created_by=None, project_id=project_id, q=None)

    merged: dict[str, dict[str, Any]] = {}
    for item in own + shared:
        wid = str(item.get("id") or "").strip()
        if wid and wid not in merged:
            merged[wid] = item
    if not merged:
        return None

    scored = sorted(
        [(_wizard_candidate_score(query, w), w) for w in merged.values()],
        key=lambda x: x[0],
        reverse=True,
    )
    best_score, best = scored[0]
    if best_score <= 0 and "wizard" not in (query or "").lower():
        return None
    return best


def _build_wizard_response(
    session: dict[str, Any],
    wizard: dict[str, Any],
    step: dict[str, Any] | None,
    message: str,
    events: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    steps = get_wizard_steps(str(wizard.get("id") or ""), created_by=None)
    current_step = int(session.get("current_step") or 1)
    is_completed = str(session.get("status") or "").lower() == "completed"
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []

    ordered_steps = sorted(steps, key=lambda s: int(s.get("step_no") or 0))
    for idx, wizard_step in enumerate(ordered_steps):
        step_no = int(wizard_step.get("step_no") or 0)
        node_id = f"s{step_no}"
        state = "pending"
        if is_completed or step_no < current_step:
            state = "completed"
        elif step_no == current_step and not is_completed:
            state = "current"
        nodes.append(
            {
                "id": node_id,
                "step_no": step_no,
                "label": str(wizard_step.get("title") or f"Step {step_no}"),
                "state": state,
            }
        )
        if idx > 0:
            prev_no = int(ordered_steps[idx - 1].get("step_no") or 0)
            edges.append({"from": f"s{prev_no}", "to": node_id})

    mermaid_lines = ["flowchart TD"]
    for node in nodes:
        mermaid_lines.append(f"  {node['id']}[{node['step_no']}. {node['label']}]")
    for edge in edges:
        mermaid_lines.append(f"  {edge['from']} --> {edge['to']}")
    if nodes:
        completed_ids = [n["id"] for n in nodes if n["state"] == "completed"]
        current_ids = [n["id"] for n in nodes if n["state"] == "current"]
        pending_ids = [n["id"] for n in nodes if n["state"] == "pending"]
        if completed_ids:
            mermaid_lines.append(f"  class {','.join(completed_ids)} completed")
        if current_ids:
            mermaid_lines.append(f"  class {','.join(current_ids)} current")
        if pending_ids:
            mermaid_lines.append(f"  class {','.join(pending_ids)} pending")
        mermaid_lines.append("  classDef completed fill:#dcfce7,stroke:#16a34a,color:#166534")
        mermaid_lines.append("  classDef current fill:#dbeafe,stroke:#2563eb,color:#1e3a8a")
        mermaid_lines.append("  classDef pending fill:#f3f4f6,stroke:#9ca3af,color:#374151")

    return {
        "message": message,
        "wizard_session": {
            "session_id": session.get("id"),
            "wizard_id": wizard.get("id"),
            "wizard_name": wizard.get("name"),
            "project_id": session.get("project_id"),
            "current_step": session.get("current_step"),
            "status": session.get("status"),
            "total_steps": wizard.get("total_steps"),
        },
        "wizard_step": step,
        "wizard_flowchart": {
            "nodes": nodes,
            "edges": edges,
            "mermaid": "\n".join(mermaid_lines),
        },
        "events": events or [],
        "violations": [],
        "violations_logged": 0,
        "suggestions": {"templates": [], "wizards": []},
        "llm_fallback": {
            "enabled": False,
            "requires_confirmation": False,
            "used": False,
            "answer": None,
        },
        "retrieved": [],
    }


def start_wizard_conversation(
    query: str,
    developer: str,
    created_by: str | None = None,
    project_id: str | None = None,
    wizard_id: str | None = None,
) -> dict[str, Any]:
    wizard: dict[str, Any] | None = None
    if wizard_id:
        all_candidates = list_wizards(created_by=None, project_id=project_id, q=None)
        wizard = next((w for w in all_candidates if str(w.get("id")) == str(wizard_id)), None)
    if wizard is None:
        wizard = _find_best_wizard_for_query(query=query, created_by=created_by, project_id=project_id)
    if wizard is None:
        return {
            "message": "No matching wizard found. Ask an architect to save a relevant step-by-step wizard.",
            "wizard_session": None,
            "wizard_step": None,
            "events": [],
            "violations": [],
            "violations_logged": 0,
            "suggestions": {"templates": [], "wizards": []},
            "llm_fallback": {
                "enabled": False,
                "requires_confirmation": False,
                "used": False,
                "answer": None,
            },
            "retrieved": [],
        }

    active = get_active_wizard_session(developer=developer, project_id=project_id)
    if active and str(active.get("wizard_id")) == str(wizard.get("id")):
        steps = get_wizard_steps(str(wizard.get("id")), created_by=None)
        curr = int(active.get("current_step") or 1)
        step = next((s for s in steps if int(s.get("step_no") or 0) == curr), None)
        events = list_wizard_session_events(str(active.get("id")), limit=20)
        message = _wizard_step_card(step, int(wizard.get("total_steps") or len(steps) or 1)) if step else "Wizard session resumed."
        update_wizard_session(str(active.get("id")), last_bot_message=message)
        return _build_wizard_response(active, wizard, step, message, events)

    session = start_wizard_session(
        wizard_id=str(wizard.get("id")),
        developer=developer,
        project_id=project_id,
    )
    steps = get_wizard_steps(str(wizard.get("id")), created_by=None)
    step = next((s for s in steps if int(s.get("step_no") or 0) == 1), None)
    message = _wizard_step_card(step, int(wizard.get("total_steps") or len(steps) or 1)) if step else "Wizard started, but no steps were found."
    add_wizard_session_event(str(session.get("id")), sender="bot", event_type="wizard_started", step_no=1, message=message)
    update_wizard_session(str(session.get("id")), current_step=1, status="active", last_bot_message=message)
    events = list_wizard_session_events(str(session.get("id")), limit=20)
    session = get_wizard_session(str(session.get("id")), developer=developer) or session
    return _build_wizard_response(session, wizard, step, message, events)


def advance_wizard_conversation(
    session_id: str,
    developer: str,
    user_message: str = "",
) -> dict[str, Any]:
    session = get_wizard_session(session_id=session_id, developer=developer)
    if session is None:
        return {
            "message": "Wizard session not found.",
            "wizard_session": None,
            "wizard_step": None,
            "events": [],
            "violations": [],
            "violations_logged": 0,
            "suggestions": {"templates": [], "wizards": []},
            "llm_fallback": {
                "enabled": False,
                "requires_confirmation": False,
                "used": False,
                "answer": None,
            },
            "retrieved": [],
        }

    if str(session.get("status") or "").lower() != "active":
        wizard_done = next(
            (w for w in list_wizards(created_by=None, project_id=session.get("project_id")) if str(w.get("id")) == str(session.get("wizard_id"))),
            None,
        )
        return _build_wizard_response(
            session,
            wizard_done or {"id": session.get("wizard_id"), "name": "Wizard", "total_steps": session.get("current_step")},
            None,
            "This wizard session is already completed.",
            list_wizard_session_events(str(session.get("id")), limit=20),
        )

    wizard = next(
        (w for w in list_wizards(created_by=None, project_id=session.get("project_id")) if str(w.get("id")) == str(session.get("wizard_id"))),
        None,
    )
    if wizard is None:
        return _build_wizard_response(session, {"id": session.get("wizard_id"), "name": "Wizard", "total_steps": 0}, None, "Wizard definition not found.")

    if user_message.strip():
        add_wizard_session_event(
            str(session.get("id")),
            sender="developer",
            event_type="user_reply",
            step_no=int(session.get("current_step") or 1),
            message=user_message.strip(),
        )

    steps = get_wizard_steps(str(wizard.get("id")), created_by=None)
    total_steps = int(wizard.get("total_steps") or len(steps) or 1)
    current_step_no = int(session.get("current_step") or 1)
    current_step = next((s for s in steps if int(s.get("step_no") or 0) == current_step_no), None)

    if not _is_done_signal(user_message):
        message = _wizard_step_card(current_step, total_steps) if current_step else "Current step not found."
        update_wizard_session(str(session.get("id")), last_bot_message=message)
        add_wizard_session_event(
            str(session.get("id")),
            sender="bot",
            event_type="wizard_prompt_repeat",
            step_no=current_step_no,
            message=message,
        )
        session = get_wizard_session(str(session.get("id")), developer=developer) or session
        return _build_wizard_response(
            session,
            wizard,
            current_step,
            message,
            list_wizard_session_events(str(session.get("id")), limit=20),
        )

    next_step_no = current_step_no + 1
    next_step = next((s for s in steps if int(s.get("step_no") or 0) == next_step_no), None)

    if next_step is None:
        completion_message = "Great. You completed all wizard steps. Wizard flow is finished."
        update_wizard_session(
            str(session.get("id")),
            current_step=current_step_no,
            status="completed",
            last_bot_message=completion_message,
        )
        add_wizard_session_event(
            str(session.get("id")),
            sender="bot",
            event_type="wizard_completed",
            step_no=current_step_no,
            message=completion_message,
        )
        session = get_wizard_session(str(session.get("id")), developer=developer) or session
        return _build_wizard_response(
            session,
            wizard,
            None,
            completion_message,
            list_wizard_session_events(str(session.get("id")), limit=20),
        )

    next_message = _wizard_step_card(next_step, total_steps)
    update_wizard_session(
        str(session.get("id")),
        current_step=next_step_no,
        status="active",
        last_bot_message=next_message,
    )
    add_wizard_session_event(
        str(session.get("id")),
        sender="bot",
        event_type="wizard_advanced",
        step_no=next_step_no,
        message=next_message,
    )
    session = get_wizard_session(str(session.get("id")), developer=developer) or session
    return _build_wizard_response(
        session,
        wizard,
        next_step,
        next_message,
        list_wizard_session_events(str(session.get("id")), limit=20),
    )


def get_wizard_conversation_status(
    developer: str,
    project_id: str | None = None,
    session_id: str | None = None,
) -> dict[str, Any]:
    session = (
        get_wizard_session(session_id=session_id, developer=developer)
        if session_id
        else get_active_wizard_session(developer=developer, project_id=project_id)
    )
    if session is None:
        return {
            "message": "No active wizard session.",
            "wizard_session": None,
            "wizard_step": None,
            "events": [],
            "violations": [],
            "violations_logged": 0,
            "suggestions": {"templates": [], "wizards": []},
            "llm_fallback": {
                "enabled": False,
                "requires_confirmation": False,
                "used": False,
                "answer": None,
            },
            "retrieved": [],
        }

    wizard = next(
        (w for w in list_wizards(created_by=None, project_id=session.get("project_id")) if str(w.get("id")) == str(session.get("wizard_id"))),
        None,
    ) or {"id": session.get("wizard_id"), "name": "Wizard", "total_steps": session.get("current_step")}
    steps = get_wizard_steps(str(session.get("wizard_id")), created_by=None)
    current_step = next((s for s in steps if int(s.get("step_no") or 0) == int(session.get("current_step") or 1)), None)
    message = str(session.get("last_bot_message") or "").strip()
    if not message:
        message = _wizard_step_card(current_step, int(wizard.get("total_steps") or len(steps) or 1)) if current_step else "Wizard session loaded."
    return _build_wizard_response(
        session,
        wizard,
        current_step,
        message,
        list_wizard_session_events(str(session.get("id")), limit=20),
    )


def _maybe_handle_wizard_assist(
    query: str,
    developer: str,
    created_by: str | None,
    project_id: str | None,
) -> dict[str, Any] | None:
    q = (query or "").strip()
    q_low = q.lower()
    # Explicit validation must never be hijacked by active wizard sessions.
    if _is_validation_query(q):
        return None
    active = get_active_wizard_session(developer=developer, project_id=project_id)
    if active:
        if _is_done_signal(q_low):
            return advance_wizard_conversation(session_id=str(active.get("id")), developer=developer, user_message=q)
        if _is_status_signal(q_low):
            return get_wizard_conversation_status(developer=developer, project_id=project_id, session_id=str(active.get("id")))
        current = get_wizard_conversation_status(developer=developer, project_id=project_id, session_id=str(active.get("id")))
        current["message"] = (
            f"You are in an active wizard session. {current.get('message')}\n"
            "Reply 'done' after you complete and activate this step."
        )
        return current

    wants_wizard = (
        "wizard" in q_low
        or "rap" in q_low
        or "step by step" in q_low
        or "guide me" in q_low
        or ("steps" in q_low and "application" in q_low)
    )
    if not wants_wizard:
        return None
    return start_wizard_conversation(query=q, developer=developer, created_by=created_by, project_id=project_id)


def assist_with_rules(
    query: str,
    code: str = "",
    object_name: str = "ADT_OBJECT",
    project_id: str | None = None,
    pack_name: str | None = None,
    developer: str = "name@zalaris.com",
    transport: str = "",
    created_by: str | None = None,
    top_k: int = 5,
    log_violations: bool = True,
    llm_fallback_confirmed: bool = False,
) -> dict[str, Any]:
    wizard_response = _maybe_handle_wizard_assist(
        query=query,
        developer=developer,
        created_by=created_by,
        project_id=project_id,
    )
    if wizard_response is not None:
        return wizard_response

    rule_rows = _load_rule_rows(project_id=project_id, pack_name=pack_name, created_by=created_by)
    resolved = [rule for row in rule_rows if (rule := _resolve_rule(row)) is not None]
    is_validate = _is_validation_query(query)

    ranked, relevance_scores = _rank_rules(
        query,
        resolved,
        is_validate=is_validate,
        developer=developer,
    )
    merged = ranked

    retrieved = merged[: max(1, min(top_k, 10))]
    violations = _validate_code(code, resolved) if is_validate else []
    logged = 0
    if log_violations and violations:
        logged = _log_violations_to_dashboard(
            violations=violations,
            object_name=object_name,
            transport=transport,
            developer=developer,
        )

    # Validation flow must stay on rule retrieval + code checks, never template/wizard suggestion mode.
    wants_template = (not is_validate) and _is_template_or_wizard_request(query)
    if wants_template:
        template_pool = [r for r in retrieved if r.rule_type in {"template", "wizard"}]
        if not template_pool:
            template_pool = [r for r in resolved if r.rule_type in {"template", "wizard"}]
        suggestions = _build_suggestions_for_query(query, template_pool, top_k=min(3, top_k))
    else:
        suggestions = {"templates": [], "wizards": []}

    llm_fallback_enabled = get_ai_llm_fallback_enabled(default=False)
    satisfactory = (
        bool(violations)
        or (wants_template and (bool(suggestions["templates"]) or bool(suggestions["wizards"])))
        or (not wants_template and bool(ranked))
    )
    llm_fallback = {
        "enabled": llm_fallback_enabled,
        "requires_confirmation": False,
        "used": False,
        "answer": None,
    }

    if llm_fallback_enabled and not is_validate and not satisfactory:
        if not llm_fallback_confirmed:
            llm_fallback["requires_confirmation"] = True
        else:
            llm_answer = _generate_llm_fallback_answer(
                query=query,
                code=code,
                retrieved=retrieved,
                suggestions=suggestions,
                top_k=top_k,
                developer=developer,
            )
            if llm_answer:
                llm_fallback["used"] = True
                llm_fallback["answer"] = llm_answer

    if violations:
        message = f"Validation failed: {len(violations)} violation(s) found."
    elif is_validate:
        message = "Validation passed: no violations found."
    elif llm_fallback["requires_confirmation"]:
        message = (
            "I could not find a satisfactory rule-based answer. "
            "Do you want me to fetch guidance from the LLM?"
        )
    elif llm_fallback["used"]:
        message = "Rule matches were insufficient. Generated guidance from LLM fallback."
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
        "llm_fallback": llm_fallback,
        "retrieved": [
            {
                "rule_id": rule.rule_id,
                "type": rule.rule_type,
                "title": rule.title,
                "severity": rule.severity,
                "rule_pack": rule.rule_pack,
                "description": rule.description,
                "selector_pattern": rule.selector_pattern,
                "relevance": round(float(relevance_scores.get(rule.rule_id, 0.0)), 3),
            }
            for rule in retrieved
        ],
    }


def explain_abap_code(
    code: str,
    object_name: str = "ADT_OBJECT",
    developer: str = "name@zalaris.com",
    created_by: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    del created_by, project_id  # kept for API parity/traceability
    cleaned_code = (code or "").strip()
    if not cleaned_code:
        return {
            "message": "No ABAP code provided to explain.",
            "object_name": object_name,
            "explanation": "",
        }

    client = _get_embed_client()
    if client is None:
        return {
            "message": "LLM is not configured. Set model API key in Settings to use Explain.",
            "object_name": object_name,
            "explanation": "",
        }

    model = get_ai_model_name(default="gpt-4.1-mini")
    explain_prompt = (
        "Act as a senior SAP solution architect.\n\n"
        "Explain the following ABAP code in a way that is understandable to:\n"
        "- Technical consultants\n"
        "- Functional consultants\n"
        "- Business users with no technical background\n\n"
        "Structure your explanation in the following sections:\n\n"
        "1. Business Context\n"
        "   - What business process does this support?\n"
        "   - Where in SAP would this typically be used? (e.g., SD, MM, FI, HCM, custom Z process)\n"
        "   - What problem is it solving?\n\n"
        "2. Business Purpose\n"
        "   - Why does this code exist?\n"
        "   - What business risk or inefficiency does it address?\n"
        "   - What would happen if this logic did not exist?\n\n"
        "3. High-Level Functional Flow (Non-Technical)\n"
        "   - Explain step-by-step what the program does in plain English.\n"
        "   - Avoid ABAP syntax in this section.\n"
        "   - Use business language.\n\n"
        "4. Technical Breakdown (For Consultants)\n"
        "   - Key tables used and why\n"
        "   - Important logic blocks (SELECT, LOOP, BADI, BAPI, enhancements, etc.)\n"
        "   - Performance considerations\n"
        "   - Error handling approach\n"
        "   - Dependencies (custom tables, config, user exits, etc.)\n\n"
        "5. Inputs and Outputs\n"
        "   - What triggers this program?\n"
        "   - What data goes in?\n"
        "   - What data comes out?\n"
        "   - Does it update database tables or only display information?\n\n"
        "6. Risks and Control Considerations\n"
        "   - Data integrity risks\n"
        "   - Performance risks\n"
        "   - Authorization considerations\n\n"
        "7. Summary in One Paragraph\n"
        "   - A short executive-level explanation of what this code does.\n\n"
        "Here is the ABAP code:\n"
        f"{cleaned_code}"
    )
    messages = [
        {
            "role": "system",
            "content": "You are a senior SAP solution architect specializing in ABAP and business process design.",
        },
        {"role": "user", "content": explain_prompt},
    ]

    try:
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.2,
            max_tokens=1200,
        )
        in_tokens, out_tokens, total_tokens = _extract_usage_tokens(getattr(response, "usage", None))
        if total_tokens > 0:
            log_llm_usage_event(
                developer=developer,
                feature="abap_code_explain",
                provider="openai",
                model=model,
                input_tokens=in_tokens,
                output_tokens=out_tokens,
                total_tokens=total_tokens,
                metadata={"object_name": object_name, "code_chars": len(cleaned_code)},
            )
        content = response.choices[0].message.content if response.choices else ""
        explanation = (content or "").strip()
        if not explanation:
            return {
                "message": "Explain request completed but returned empty content.",
                "object_name": object_name,
                "explanation": "",
            }
        return {
            "message": "ABAP explanation generated.",
            "object_name": object_name,
            "explanation": explanation,
        }
    except Exception as ex:
        return {
            "message": f"Explain request failed: {str(ex)}",
            "object_name": object_name,
            "explanation": "",
        }
