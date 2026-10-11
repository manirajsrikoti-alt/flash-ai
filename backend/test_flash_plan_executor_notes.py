"""Tests for _create_note() in flash_plan_executor.

All tests mock subprocess.run — no real Apple Notes are opened or created.
"""
import json
import os
import unittest
from unittest.mock import patch, MagicMock

from flash_plan_executor import (
    _create_note,
    _CREATE_NOTE_SCRIPT,
    execute_step,
)


def _make_proc(returncode: int, stdout: str) -> MagicMock:
    proc = MagicMock()
    proc.returncode = returncode
    proc.stdout = stdout
    return proc


def _success_stdout(title: str = "My Note") -> str:
    return json.dumps({"success": True, "title": title})


class CreateNoteValidationTests(unittest.TestCase):
    """Input validation — no subprocess calls should be made."""

    def test_empty_title_rejected(self):
        result = _create_note("", "body")
        self.assertFalse(result.ok)
        self.assertIn("must not be empty", result.message)

    def test_whitespace_only_title_rejected(self):
        result = _create_note("   ", "body")
        self.assertFalse(result.ok)
        self.assertIn("must not be empty", result.message)

    def test_non_string_title_rejected(self):
        result = _create_note(None, "body")   # type: ignore[arg-type]
        self.assertFalse(result.ok)
        self.assertIn("title must be a string", result.message)

    def test_non_string_body_rejected(self):
        result = _create_note("Hello", 42)   # type: ignore[arg-type]
        self.assertFalse(result.ok)
        self.assertIn("body must be a string", result.message)

    def test_title_too_long_rejected(self):
        result = _create_note("x" * 201, "body")
        self.assertFalse(result.ok)
        self.assertIn("exceeds maximum length", result.message)

    def test_body_too_long_rejected(self):
        result = _create_note("Hello", "x" * 10_001)
        self.assertFalse(result.ok)
        self.assertIn("exceeds maximum length", result.message)

    def test_null_byte_in_title_rejected(self):
        result = _create_note("Hel\x00lo", "body")
        self.assertFalse(result.ok)
        self.assertIn("null byte", result.message)

    def test_null_byte_in_body_rejected(self):
        result = _create_note("Hello", "bad\x00body")
        self.assertFalse(result.ok)
        self.assertIn("null byte", result.message)

    def test_title_at_max_length_allowed(self):
        """Exactly 200-character title must pass validation (subprocess mocked)."""
        with patch("flash_plan_executor.subprocess.run") as mock_run:
            mock_run.return_value = _make_proc(0, _success_stdout())
            result = _create_note("x" * 200, "body")
        self.assertTrue(result.ok)

    def test_body_at_max_length_allowed(self):
        """Exactly 10 000-character body must pass validation (subprocess mocked)."""
        with patch("flash_plan_executor.subprocess.run") as mock_run:
            mock_run.return_value = _make_proc(0, _success_stdout())
            result = _create_note("Hello", "x" * 10_000)
        self.assertTrue(result.ok)


class CreateNoteSpecialCharacterTests(unittest.TestCase):
    """Shell metacharacters and other special text must be accepted as data."""

    @patch("flash_plan_executor.subprocess.run")
    def _run_with_special(self, title, body, mock_run):
        mock_run.return_value = _make_proc(0, _success_stdout(title.strip()))
        result = _create_note(title, body)
        return result, mock_run

    def test_semicolon_in_title(self):
        result, mock_run = self._run_with_special("Note; important", "body")
        self.assertTrue(result.ok)
        # Title must appear only in env, never in the script argument
        _, kwargs = mock_run.call_args
        self.assertEqual(kwargs["env"]["FLASH_NOTE_TITLE"], "Note; important")
        self.assertNotIn("Note; important", kwargs["env"].get("-e", _CREATE_NOTE_SCRIPT))

    def test_dollar_sign_in_body(self):
        result, mock_run = self._run_with_special("Hello", "Cost: $100")
        self.assertTrue(result.ok)
        _, kwargs = mock_run.call_args
        self.assertEqual(kwargs["env"]["FLASH_NOTE_BODY"], "Cost: $100")

    def test_ampersand_in_body(self):
        result, mock_run = self._run_with_special("Hello", "Fish & chips")
        self.assertTrue(result.ok)
        _, kwargs = mock_run.call_args
        self.assertEqual(kwargs["env"]["FLASH_NOTE_BODY"], "Fish & chips")

    def test_double_quotes_in_body(self):
        result, mock_run = self._run_with_special('My Note', 'He said "hello"')
        self.assertTrue(result.ok)
        _, kwargs = mock_run.call_args
        self.assertEqual(kwargs["env"]["FLASH_NOTE_BODY"], 'He said "hello"')

    def test_newline_in_body(self):
        result, mock_run = self._run_with_special("Hello", "Line 1\nLine 2")
        self.assertTrue(result.ok)
        _, kwargs = mock_run.call_args
        self.assertEqual(kwargs["env"]["FLASH_NOTE_BODY"], "Line 1\nLine 2")

    def test_unicode_in_title_and_body(self):
        result, mock_run = self._run_with_special("日本語ノート", "内容テスト 🎉")
        self.assertTrue(result.ok)
        _, kwargs = mock_run.call_args
        self.assertEqual(kwargs["env"]["FLASH_NOTE_TITLE"], "日本語ノート")
        self.assertEqual(kwargs["env"]["FLASH_NOTE_BODY"], "内容テスト 🎉")


class CreateNoteScriptStaticnessTests(unittest.TestCase):
    """Assert data is passed via env vars, never embedded in the script."""

    @patch("flash_plan_executor.subprocess.run")
    def test_script_argument_is_static_constant(self, mock_run):
        """The -e script string must be the module constant, regardless of input."""
        mock_run.return_value = _make_proc(0, _success_stdout("Secret"))
        _create_note("Secret title $HOME; rm -rf /", "Secret body")

        args, kwargs = mock_run.call_args
        cmd = args[0]
        # Fifth element in the command list is the script (after -e)
        self.assertEqual(cmd[4], _CREATE_NOTE_SCRIPT)
        # Title and body must NOT appear in the static script
        self.assertNotIn("Secret title", cmd[4])
        self.assertNotIn("Secret body", cmd[4])

    @patch("flash_plan_executor.subprocess.run")
    def test_title_and_body_in_env_vars(self, mock_run):
        """Title and body must be present in env as separate variables."""
        mock_run.return_value = _make_proc(0, _success_stdout("My Note"))
        _create_note("My Note", "My body text")

        _, kwargs = mock_run.call_args
        env = kwargs["env"]
        self.assertEqual(env["FLASH_NOTE_TITLE"], "My Note")
        self.assertEqual(env["FLASH_NOTE_BODY"], "My body text")

    @patch("flash_plan_executor.subprocess.run")
    def test_parent_env_is_inherited(self, mock_run):
        """Subprocess env must extend os.environ (not replace it)."""
        mock_run.return_value = _make_proc(0, _success_stdout())
        _create_note("Hello", "body")
        _, kwargs = mock_run.call_args
        # PATH should still be present from os.environ
        self.assertIn("PATH", kwargs["env"])


class CreateNoteSuccessTests(unittest.TestCase):
    """Happy-path subprocess outcomes."""

    @patch("flash_plan_executor.subprocess.run")
    def test_success_result_ok(self, mock_run):
        mock_run.return_value = _make_proc(0, _success_stdout("Hello"))
        result = _create_note("Hello", "World")
        self.assertTrue(result.ok)
        self.assertIn("Hello", result.message)

    @patch("flash_plan_executor.subprocess.run")
    def test_title_is_stripped_before_passing(self, mock_run):
        mock_run.return_value = _make_proc(0, _success_stdout("Hello"))
        _create_note("  Hello  ", "body")
        _, kwargs = mock_run.call_args
        self.assertEqual(kwargs["env"]["FLASH_NOTE_TITLE"], "Hello")

    @patch("flash_plan_executor.subprocess.run")
    def test_empty_body_is_allowed(self, mock_run):
        mock_run.return_value = _make_proc(0, _success_stdout("Hello"))
        result = _create_note("Hello", "")
        self.assertTrue(result.ok)

    @patch("flash_plan_executor.subprocess.run")
    def test_osascript_called_with_correct_command(self, mock_run):
        mock_run.return_value = _make_proc(0, _success_stdout())
        _create_note("Hello", "body")
        args, _ = mock_run.call_args
        cmd = args[0]
        self.assertEqual(cmd[0], "osascript")
        self.assertEqual(cmd[1], "-l")
        self.assertEqual(cmd[2], "JavaScript")
        self.assertEqual(cmd[3], "-e")
        self.assertEqual(cmd[4], _CREATE_NOTE_SCRIPT)


class CreateNoteFailureTests(unittest.TestCase):
    """Automation failure outcomes."""

    @patch("flash_plan_executor.subprocess.run")
    def test_non_zero_returncode_reports_automation_failure(self, mock_run):
        mock_run.return_value = _make_proc(1, "")
        result = _create_note("Hello", "body")
        self.assertFalse(result.ok)
        self.assertIn("Automation failed", result.message)
        self.assertIn("Automation > Notes", result.message)

    @patch("flash_plan_executor.subprocess.run")
    def test_empty_stdout_reports_failure(self, mock_run):
        mock_run.return_value = _make_proc(0, "")
        result = _create_note("Hello", "body")
        self.assertFalse(result.ok)
        self.assertIn("Empty response", result.message)

    @patch("flash_plan_executor.subprocess.run")
    def test_malformed_json_reports_failure(self, mock_run):
        mock_run.return_value = _make_proc(0, "not json {{")
        result = _create_note("Hello", "body")
        self.assertFalse(result.ok)
        self.assertIn("Malformed response", result.message)

    @patch("flash_plan_executor.subprocess.run")
    def test_jxa_error_field_reports_failure(self, mock_run):
        mock_run.return_value = _make_proc(
            0, json.dumps({"error": "Notes not running."})
        )
        result = _create_note("Hello", "body")
        self.assertFalse(result.ok)
        self.assertIn("Notes error", result.message)

    @patch("flash_plan_executor.subprocess.run")
    def test_timeout_reports_failure(self, mock_run):
        import subprocess
        mock_run.side_effect = subprocess.TimeoutExpired(cmd=["osascript"], timeout=10)
        result = _create_note("Hello", "body")
        self.assertFalse(result.ok)
        self.assertIn("Timed out", result.message)

    @patch("flash_plan_executor.subprocess.run")
    def test_missing_or_false_success_reports_failure(self, mock_run):
        mock_run.return_value = _make_proc(0, json.dumps({}))
        result = _create_note("Hello", "body")
        self.assertFalse(result.ok)
        self.assertIn("did not confirm success", result.message)

        mock_run.return_value = _make_proc(0, json.dumps({"success": False}))
        result = _create_note("Hello", "body")
        self.assertFalse(result.ok)
        self.assertIn("did not confirm success", result.message)


class ExecuteStepCreateNoteTests(unittest.TestCase):
    """Integration: execute_step dispatches create_note correctly."""

    def _note_step(self, **overrides):
        step = {
            "action": "create_note",
            "target": "Hello",
            "details": "World",
            "requires_confirmation": False,
        }
        step.update(overrides)
        return step

    def test_dry_run_returns_description(self):
        result = execute_step(self._note_step(), dry_run=True)
        self.assertTrue(result.ok)
        self.assertIn("DRY RUN", result.message)
        self.assertIn("Hello", result.message)

    @patch("flash_plan_executor.subprocess.run")
    def test_live_run_dispatches_to_create_note(self, mock_run):
        mock_run.return_value = _make_proc(0, _success_stdout("Hello"))
        result = execute_step(self._note_step(), dry_run=False)
        self.assertTrue(result.ok)
        mock_run.assert_called_once()

    def test_requires_confirmation_true_is_rejected_before_dispatch(self):
        step = self._note_step(requires_confirmation=True)
        result = execute_step(step, dry_run=False)
        self.assertFalse(result.ok)
        self.assertIn("requires confirmation", result.message)

    def test_empty_title_rejected_by_execute_step(self):
        """execute_step passes target="" to _create_note which then validates it."""
        with patch("flash_plan_executor.subprocess.run") as mock_run:
            mock_run.return_value = _make_proc(0, _success_stdout())
            result = execute_step(self._note_step(target=""), dry_run=False)
        self.assertFalse(result.ok)
        self.assertIn("must not be empty", result.message)

    @patch("flash_plan_executor.subprocess.run")
    def test_prepare_message_still_rejected(self, _mock_run):
        step = {
            "action": "prepare_message",
            "target": "Alice",
            "details": "hello",
            "requires_confirmation": False,
        }
        result = execute_step(step, dry_run=False)
        self.assertFalse(result.ok)
        self.assertIn("not executable", result.message)


if __name__ == "__main__":
    unittest.main(verbosity=2)
