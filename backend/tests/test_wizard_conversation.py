import unittest
import uuid

import yaml

from app.services import bot_service
from app.services.store_service import delete_wizard, list_projects, save_wizard


def _build_step_yaml(step_no: int, title: str, depends_on: list[int] | None = None) -> str:
    return yaml.safe_dump(
        {
            "id": f"wizard.test.step.{step_no}",
            "type": "wizard",
            "title": title,
            "severity": "MAJOR",
            "description": f"{title} description",
            "selector": {"pattern": f"test wizard step {step_no}"},
            "fix": f"Complete {title}",
            "rationale": f"{title} is required",
            "confidence": 0.9,
            "wizard": {
                "step_no": step_no,
                "step_title": title,
                "step_description": f"Implement {title}",
                "object_type": "abap_object",
                "depends_on": depends_on or [],
                "template": {
                    "language": "ABAP",
                    "snippet": f"\" {title} snippet",
                },
            },
        },
        sort_keys=False,
        width=120,
    )


class WizardConversationTests(unittest.TestCase):
    def test_wizard_conversation_lifecycle_confirmation_only(self):
        projects = list_projects()
        self.assertTrue(projects, "expected seeded projects to exist")
        project_id = str(projects[0]["id"])

        wizard_name = f"Wizard Conversation Test {uuid.uuid4().hex[:8]}"
        developer = f"dev-{uuid.uuid4().hex[:8]}@example.com"

        result = save_wizard(
            project_id=project_id,
            wizard_name=wizard_name,
            wizard_description="wizard session lifecycle test",
            total_steps=2,
            steps=[
                {"yaml": _build_step_yaml(1, "Create Root View"), "confidence": 0.9, "category": "wizard"},
                {"yaml": _build_step_yaml(2, "Create Projection View", depends_on=[1]), "confidence": 0.9, "category": "wizard"},
            ],
            created_by="name@zalaris.com",
            rule_pack="test-wizard-pack",
        )
        wizard_id = result["wizard_id"]

        try:
            started = bot_service.start_wizard_conversation(
                query=wizard_name,
                developer=developer,
                created_by="name@zalaris.com",
                project_id=project_id,
                wizard_id=wizard_id,
            )
            self.assertIsNotNone(started["wizard_session"])
            self.assertEqual(started["wizard_session"]["current_step"], 1)
            self.assertEqual(started["wizard_session"]["status"], "active")
            self.assertIsNotNone(started["wizard_step"])
            self.assertEqual(int(started["wizard_step"]["step_no"]), 1)
            self.assertIn("wizard_flowchart", started)
            self.assertTrue(started["wizard_flowchart"]["nodes"])
            self.assertIn("mermaid", started["wizard_flowchart"])
            session_id = started["wizard_session"]["session_id"]

            status_step_1 = bot_service.get_wizard_conversation_status(
                developer=developer,
                project_id=project_id,
                session_id=session_id,
            )
            self.assertEqual(status_step_1["wizard_session"]["current_step"], 1)
            self.assertIsNotNone(status_step_1["wizard_step"])
            self.assertEqual(int(status_step_1["wizard_step"]["step_no"]), 1)

            advanced = bot_service.advance_wizard_conversation(
                session_id=session_id,
                developer=developer,
                user_message="done",
            )
            self.assertEqual(advanced["wizard_session"]["current_step"], 2)
            self.assertEqual(advanced["wizard_session"]["status"], "active")
            self.assertIsNotNone(advanced["wizard_step"])
            self.assertEqual(int(advanced["wizard_step"]["step_no"]), 2)
            current_nodes = [n for n in advanced["wizard_flowchart"]["nodes"] if n.get("state") == "current"]
            self.assertEqual(len(current_nodes), 1)
            self.assertEqual(int(current_nodes[0]["step_no"]), 2)

            completed = bot_service.advance_wizard_conversation(
                session_id=session_id,
                developer=developer,
                user_message="done",
            )
            self.assertEqual(completed["wizard_session"]["status"], "completed")
            self.assertIsNone(completed["wizard_step"])
            self.assertIn("completed", completed["message"].lower())
        finally:
            delete_wizard(wizard_id, created_by="name@zalaris.com")

    def test_validation_query_bypasses_active_wizard_session(self):
        projects = list_projects()
        self.assertTrue(projects, "expected seeded projects to exist")
        project_id = str(projects[0]["id"])

        wizard_name = f"Wizard Validation Bypass {uuid.uuid4().hex[:8]}"
        developer = f"dev-{uuid.uuid4().hex[:8]}@example.com"

        result = save_wizard(
            project_id=project_id,
            wizard_name=wizard_name,
            wizard_description="ensure validation bypasses active wizard",
            total_steps=1,
            steps=[
                {"yaml": _build_step_yaml(1, "Create Root View"), "confidence": 0.9, "category": "wizard"},
            ],
            created_by="name@zalaris.com",
            rule_pack="test-wizard-pack",
        )
        wizard_id = result["wizard_id"]

        try:
            started = bot_service.start_wizard_conversation(
                query=wizard_name,
                developer=developer,
                created_by="name@zalaris.com",
                project_id=project_id,
                wizard_id=wizard_id,
            )
            self.assertIsNotNone(started["wizard_session"])
            self.assertEqual(started["wizard_session"]["status"], "active")

            response = bot_service.assist_with_rules(
                query="validate current object against governance rules",
                code="DATA lv_time TYPE catshours. lv_time = lv_time + lv_time.",
                object_name="Z_TEST_OBJECT",
                project_id=project_id,
                developer=developer,
                created_by="name@zalaris.com",
            )

            message = str(response.get("message") or "")
            self.assertNotIn("active wizard session", message.lower())
            self.assertFalse("wizard_session" in response)
        finally:
            delete_wizard(wizard_id, created_by="name@zalaris.com")


if __name__ == "__main__":
    unittest.main()
