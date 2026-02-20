from __future__ import annotations

import re
from typing import Any

import yaml


def _extract_pattern(rule_obj: dict[str, Any]) -> str | None:
    selector = rule_obj.get("selector")
    if isinstance(selector, dict):
        pattern = selector.get("pattern")
        if isinstance(pattern, str) and pattern.strip():
            return pattern.strip()
    if isinstance(selector, str) and selector.strip():
        return selector.strip()
    return None


def _rule_requires_arithmetic_try_catch(rule_obj: dict[str, Any]) -> bool:
    haystack = " ".join(
        [
            str(rule_obj.get("title") or ""),
            str(rule_obj.get("description") or ""),
            str(rule_obj.get("message") or ""),
            str(rule_obj.get("fix") or ""),
            str(rule_obj.get("rationale") or ""),
            str(rule_obj.get("selector") or ""),
            str(rule_obj),
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


def _rule_requires_try_catch(rule_obj: dict[str, Any]) -> bool:
    haystack = " ".join(
        [
            str(rule_obj.get("title") or ""),
            str(rule_obj.get("description") or ""),
            str(rule_obj.get("message") or ""),
            str(rule_obj.get("fix") or ""),
            str(rule_obj.get("rationale") or ""),
            str(rule_obj.get("selector") or ""),
            str(rule_obj),
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


def test_rule_yaml_against_code(rule_yaml: str, code: str) -> dict[str, Any]:
    try:
        rule_obj = yaml.safe_load(rule_yaml)
        if not isinstance(rule_obj, dict):
            return {
                "ok": False,
                "passed": False,
                "message": "Invalid rule YAML.",
                "detail": "Parsed rule is not an object.",
            }
    except Exception as exc:
        return {
            "ok": False,
            "passed": False,
            "message": "Invalid rule YAML.",
            "detail": str(exc),
        }

    rule_type = str(rule_obj.get("type") or "").lower()
    if rule_type == "template":
        return {
            "ok": True,
            "passed": True,
            "message": "Template rules are not testable with this feature.",
            "detail": "Skipped for template type.",
        }

    pattern = _extract_pattern(rule_obj)
    rule_message = str(
        rule_obj.get("message")
        or rule_obj.get("description")
        or "Code failed this rule."
    )

    if not code.strip():
        return {
            "ok": False,
            "passed": False,
            "message": "Provide code to test this rule.",
            "detail": "Empty test input.",
        }

    if _rule_requires_arithmetic_try_catch(rule_obj):
        unprotected = _find_unprotected_arithmetic_operation(code)
        if unprotected is not None:
            line_no, line_text = unprotected
            return {
                "ok": True,
                "passed": False,
                "message": rule_message,
                "detail": f"Unprotected arithmetic at line {line_no}: {line_text}",
            }
        return {
            "ok": True,
            "passed": True,
            "message": "Code passed this rule.",
            "detail": "Arithmetic operations appear protected by TRY...CATCH.",
        }

    if _rule_requires_try_catch(rule_obj):
        if not _code_has_try_catch_block(code):
            return {
                "ok": True,
                "passed": False,
                "message": rule_message,
                "detail": "Required TRY...CATCH...ENDTRY block is missing.",
            }
        return {
            "ok": True,
            "passed": True,
            "message": "Code passed this rule.",
            "detail": "TRY...CATCH...ENDTRY block present.",
        }

    if not pattern:
        return {
            "ok": False,
            "passed": False,
            "message": "Rule has no selector pattern; cannot auto-test.",
            "detail": "Missing selector.pattern",
        }

    try:
        matched = re.search(pattern, code, flags=re.IGNORECASE | re.MULTILINE) is not None
    except re.error:
        matched = pattern.lower() in code.lower()

    # match == violation hit
    if matched:
        return {
            "ok": True,
            "passed": False,
            "message": rule_message,
            "detail": f"Violation pattern matched: {pattern}",
        }

    return {
        "ok": True,
        "passed": True,
        "message": "Code passed this rule.",
        "detail": "No violation pattern match found.",
    }
