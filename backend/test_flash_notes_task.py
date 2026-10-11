"""Unit tests for Apple Notes task execution, routing, validation, and error propagation.

All tests mock subprocess calls — no real Apple Notes are created.
"""
import json
import unittest
from unittest.mock import MagicMock, patch

from flash_executor import execute
from flash_router import route


def _make_proc(returncode: int, stdout: str = "", stderr: str = "") -> MagicMock:
    proc = MagicMock()
    proc.returncode = returncode
    proc.stdout = stdout
    proc.stderr = stderr
    return proc


class AppleNotesRoutingTests(unittest.TestCase):
    def test_route_create_note_with_title_and_body(self):
        decision = route("create a note titled Meeting with body Discuss roadmap")
        self.assertEqual(decision.intent, "create_note")
        self.assertEqual(decision.source, "rule")
        data = json.loads(decision.target)
        self.assertEqual(data["title"], "Meeting")
        self.assertEqual(data["body"], "Discuss roadmap")

    def test_route_create_note_with_dangerous_words_in_body(self):
        # Even if the note body contains "buy milk" or "text mom", note routing succeeds safely
        decision = route("create a note titled Shopping with text buy milk")
        self.assertEqual(decision.intent, "create_note")
        data = json.loads(decision.target)
        self.assertEqual(data["title"], "Shopping")
        self.assertEqual(data["body"], "buy milk")

    def test_route_take_a_note_colon(self):
        decision = route("take a note: buy groceries for dinner")
        self.assertEqual(decision.intent, "create_note")
        data = json.loads(decision.target)
        self.assertEqual(data["body"], "buy groceries for dinner")

    def test_route_create_note_title_only(self):
        decision = route("create a note titled Work Tasks")
        self.assertEqual(decision.intent, "create_note")
        data = json.loads(decision.target)
        self.assertEqual(data["title"], "Work Tasks")

    def test_dangerous_note_commands_rejected(self):
        # "delete my notes" is dangerous and must NOT route to create_note
        decision = route("delete my notes")
        self.assertEqual(decision.intent, "unknown")
        self.assertEqual(decision.source, "rejected")


class AppleNotesExecutorTests(unittest.TestCase):
    @patch("flash_plan_executor.subprocess.run")
    def test_create_note_success(self, mock_run):
        mock_run.return_value = _make_proc(0, json.dumps({"success": True, "title": "Meeting"}))
        result = execute("create_note", {"title": "Meeting", "body": "Discuss roadmap"})
        self.assertTrue(result.ok)
        self.assertIn("Created Notes note: 'Meeting'", result.message)

    @patch("flash_plan_executor.subprocess.run")
    def test_create_note_from_json_string(self, mock_run):
        mock_run.return_value = _make_proc(0, json.dumps({"success": True, "title": "Project"}))
        target_str = json.dumps({"title": "Project", "body": "Alpha release"})
        result = execute("create_note", target_str)
        self.assertTrue(result.ok)
        self.assertIn("Created Notes note: 'Project'", result.message)

    @patch("flash_plan_executor.subprocess.run")
    def test_create_note_from_separated_string(self, mock_run):
        mock_run.return_value = _make_proc(0, json.dumps({"success": True, "title": "Ideas"}))
        result = execute("create_note", "Ideas::Brainstorming session")
        self.assertTrue(result.ok)
        self.assertIn("Created Notes note: 'Ideas'", result.message)

    def test_create_note_empty_title_rejected(self):
        result = execute("create_note", "")
        self.assertFalse(result.ok)
        self.assertIn("must not be empty", result.message)

    @patch("flash_plan_executor.subprocess.run")
    def test_create_note_jxa_automation_permission_error(self, mock_run):
        mock_run.return_value = _make_proc(1, stderr="Not authorized to send Apple events")
        result = execute("create_note", {"title": "Test", "body": "Body"})
        self.assertFalse(result.ok)
        self.assertIn("Automation failed", result.message)

    @patch("flash_plan_executor.subprocess.run")
    def test_create_note_jxa_internal_error(self, mock_run):
        mock_run.return_value = _make_proc(0, json.dumps({"error": "Notes is not responding"}))
        result = execute("create_note", {"title": "Test", "body": "Body"})
        self.assertFalse(result.ok)
        self.assertIn("Notes error: Notes is not responding", result.message)


if __name__ == "__main__":
    unittest.main(verbosity=2)
