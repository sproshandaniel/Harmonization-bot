import unittest
from unittest.mock import patch

from app.services.bot_service import ResolvedRule, assist_with_rules


def _rule(rule_id: str, rule_type: str, title: str, pattern: str, snippet: str = "") -> ResolvedRule:
    return ResolvedRule(
        rule_id=rule_id,
        rule_type=rule_type,
        title=title,
        description=title,
        message=title,
        severity="MAJOR",
        selector_pattern=pattern,
        fix="fix",
        rationale="rationale",
        rule_pack="test-pack",
        template_snippet=snippet if rule_type == "template" else "",
        wizard_snippet=snippet if rule_type == "wizard" else "",
        subtags=["code"] if rule_type == "code" else [],
        metadata={},
        raw_yaml=f"type: {rule_type}\ntitle: {title}",
    )


class AssistRoutingTests(unittest.TestCase):
    @patch("app.services.bot_service._maybe_handle_wizard_assist", return_value=None)
    @patch("app.services.bot_service.get_ai_llm_fallback_enabled", return_value=False)
    @patch("app.services.bot_service._load_rule_rows", return_value=[{"id": "stub"}])
    def test_validation_stays_in_rule_validation_flow(self, _rows, _llm, _wizard):
        mocked_rules = [
            _rule("rule.code.1", "code", "No direct self-addition", r"\blv_time\s*=\s*lv_time\s*\+\s*lv_time\b"),
            _rule("rule.template.1", "template", "Sample template", r"template", "WRITE: / 'X'."),
            _rule("rule.wizard.1", "wizard", "Wizard step", r"wizard", "define behavior ..."),
        ]
        with patch("app.services.bot_service._resolve_rule", side_effect=mocked_rules):
            response = assist_with_rules(
                query="validate current object against governance rules",
                code="DATA : lv_time TYPE catshours. lv_time = lv_time + lv_time.",
                object_name="Z_OBJ",
                developer="dev@example.com",
                created_by="dev@example.com",
            )

        self.assertIn("validation", str(response.get("message", "")).lower())
        self.assertIsInstance(response.get("violations"), list)
        self.assertGreaterEqual(len(response.get("violations", [])), 1)
        self.assertEqual(response.get("suggestions"), {"templates": [], "wizards": []})

    @patch("app.services.bot_service._maybe_handle_wizard_assist", return_value=None)
    @patch("app.services.bot_service.get_ai_llm_fallback_enabled", return_value=False)
    @patch("app.services.bot_service._load_rule_rows", return_value=[{"id": "stub"}])
    def test_template_wizard_query_returns_template_wizard_matches(self, _rows, _llm, _wizard):
        mocked_rules = [
            _rule("rule.code.1", "code", "Code rule", r"forbidden"),
            _rule("rule.template.1", "template", "Employee fetch template", r"employee fetch", "SELECT ..."),
            _rule("rule.wizard.1", "wizard", "RAP setup wizard", r"rap wizard", "define behavior ..."),
        ]
        with patch("app.services.bot_service._resolve_rule", side_effect=mocked_rules):
            response = assist_with_rules(
                query="give me employee fetch template and rap wizard",
                code="",
                object_name="Z_OBJ",
                developer="dev@example.com",
                created_by="dev@example.com",
            )

        suggestions = response.get("suggestions", {})
        self.assertIsInstance(suggestions, dict)
        self.assertIn("templates", suggestions)
        self.assertIn("wizards", suggestions)
        self.assertEqual(response.get("violations"), [])
        retrieved_types = {item.get("type") for item in response.get("retrieved", [])}
        if retrieved_types:
            self.assertTrue(retrieved_types.issubset({"template", "wizard"}))


if __name__ == "__main__":
    unittest.main()
