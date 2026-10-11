"""Unit tests for WhatsApp task execution, recipient resolution, confirmation flow, and safety gates.

All tests mock subprocess calls — no real messages are opened or sent.
"""
import unittest
from unittest.mock import MagicMock, patch

from flash_cli import parse_whatsapp_request, BLOCKED_PATTERN
from flash_context import TaskContext
from flash_executor import execute, prepare_whatsapp_message
from flash_router import route


def _make_proc(returncode: int, stdout: str = "", stderr: str = "") -> MagicMock:
    proc = MagicMock()
    proc.returncode = returncode
    proc.stdout = stdout
    proc.stderr = stderr
    return proc


class WhatsAppParsingTests(unittest.TestCase):
    def test_open_whatsapp_is_not_messaging(self):
        self.assertIsNone(parse_whatsapp_request("open whatsapp"))
        self.assertIsNone(parse_whatsapp_request("launch WhatsApp app"))
        self.assertEqual(route("open whatsapp").intent, "open_whatsapp")

    def test_parse_complete_message_saying(self):
        req = parse_whatsapp_request("send a whatsapp message to Alice saying I will be late")
        self.assertIsNotNone(req)
        self.assertEqual(req["recipient"], "Alice")
        self.assertEqual(req["message"], "I will be late")

    def test_parse_complete_message_colon(self):
        req = parse_whatsapp_request("send a whatsapp to Bob: meeting at 3 pm")
        self.assertIsNotNone(req)
        self.assertEqual(req["recipient"], "Bob")
        self.assertEqual(req["message"], "meeting at 3 pm")

    def test_parse_complete_message_on_whatsapp(self):
        req = parse_whatsapp_request("message Charlie on whatsapp saying hello there")
        self.assertIsNotNone(req)
        self.assertEqual(req["recipient"], "Charlie")
        self.assertEqual(req["message"], "hello there")

    def test_parse_missing_message(self):
        req = parse_whatsapp_request("send a whatsapp message to Dave")
        self.assertIsNotNone(req)
        self.assertEqual(req["recipient"], "Dave")
        self.assertIsNone(req["message"])

    def test_parse_missing_recipient(self):
        req = parse_whatsapp_request("send a whatsapp message saying hello")
        self.assertIsNotNone(req)
        self.assertIsNone(req["recipient"])
        self.assertEqual(req["message"], "hello")

    def test_unsupported_or_dangerous_messaging_not_parsed_as_whatsapp(self):
        # Email, generic messages without WhatsApp, etc. must return None so they hit BLOCKED_PATTERN
        self.assertIsNone(parse_whatsapp_request("send an email to Alice"))
        self.assertIsNone(parse_whatsapp_request("Send a message to my professor"))
        self.assertIsNone(parse_whatsapp_request("text Dave"))
        self.assertIsNone(parse_whatsapp_request("Delete all my files"))


class WhatsAppExecutorTests(unittest.TestCase):
    @patch("flash_executor.subprocess.run")
    def test_prepare_message_success_and_limitation_disclosure(self, mock_run):
        mock_run.return_value = _make_proc(0)
        result = prepare_whatsapp_message("Alice", "I will be late")
        self.assertTrue(result.ok)
        self.assertIn("Opened WhatsApp with draft for Alice", result.message)
        self.assertIn("macOS WhatsApp does not support automatic sending", result.message)
        # Verify safe URL scheme was used
        args, _ = mock_run.call_args
        self.assertEqual(args[0], ["open", "whatsapp://send?text=I+will+be+late"])

    @patch("flash_executor.subprocess.run")
    def test_prepare_message_phone_number(self, mock_run):
        mock_run.return_value = _make_proc(0)
        result = prepare_whatsapp_message("+1 (555) 012-3456", "Hello")
        self.assertTrue(result.ok)
        args, _ = mock_run.call_args
        self.assertIn("phone=15550123456", args[0][1])

    def test_validation_empty_recipient_rejected(self):
        result = prepare_whatsapp_message("", "Hello")
        self.assertFalse(result.ok)
        self.assertIn("Recipient is required", result.message)

    def test_validation_empty_message_rejected(self):
        result = prepare_whatsapp_message("Alice", "")
        self.assertFalse(result.ok)
        self.assertIn("Message content is required", result.message)

    def test_validation_control_characters_rejected(self):
        result = prepare_whatsapp_message("Alice", "Hello\x00world")
        self.assertFalse(result.ok)
        self.assertIn("invalid control characters", result.message)


class WhatsAppConfirmationAndSafetyTests(unittest.TestCase):
    def test_safety_gate_blocks_generic_and_email_messaging(self):
        # Non-WhatsApp messaging commands MUST be blocked by BLOCKED_PATTERN
        for cmd in [
            "Send a message to my professor",
            "send an email to Alice",
            "text 555-1234",
            "delete all notes",
        ]:
            with self.subTest(cmd=cmd):
                self.assertIsNotNone(BLOCKED_PATTERN.search(cmd))

    @patch("builtins.print")
    @patch("flash_executor.subprocess.run")
    def test_cli_whatsapp_requires_confirmation_before_sending(self, mock_run, mock_print):
        mock_run.return_value = _make_proc(0)
        import flash_cli
        from flash_aws_brain import FlashAWSBrain

        inputs = [
            {"type": "final", "text": "send a whatsapp message to Alice saying I will be late"},
            {"type": "final", "text": "no"},  # User cancels!
            {"type": "final", "text": "quit"}
        ]

        def mock_listen():
            for item in inputs:
                yield item
            while True:
                yield {"type": "final", "text": "quit"}

        args = MagicMock()
        args.voice = True
        brain = FlashAWSBrain()
        task_context = TaskContext()

        flash_cli._run_loop(args, mock_listen(), brain, task_context)

        # Because the user said 'no', subprocess.run must NEVER have been called to open WhatsApp
        mock_run.assert_not_called()
        printed = [" ".join(str(a) for a in call[0]) for call in mock_print.call_args_list]
        self.assertTrue(any("Would you like to proceed?" in line for line in printed))
        self.assertTrue(any("Action cancelled." in line for line in printed))

    @patch("builtins.print")
    @patch("flash_executor.subprocess.run")
    def test_cli_whatsapp_proceeds_after_yes_confirmation(self, mock_run, mock_print):
        mock_run.return_value = _make_proc(0)
        import flash_cli
        from flash_aws_brain import FlashAWSBrain

        inputs = [
            {"type": "final", "text": "send a whatsapp message to Alice saying I will be late"},
            {"type": "final", "text": "yes"},  # User confirms!
            {"type": "final", "text": "quit"}
        ]

        def mock_listen():
            for item in inputs:
                yield item
            while True:
                yield {"type": "final", "text": "quit"}

        args = MagicMock()
        args.voice = True
        brain = FlashAWSBrain()
        task_context = TaskContext()

        flash_cli._run_loop(args, mock_listen(), brain, task_context)

        # After user says 'yes', WhatsApp was drafted
        mock_run.assert_called_once()
        args_called, _ = mock_run.call_args
        self.assertIn("whatsapp://send", args_called[0][1])
        printed = [" ".join(str(a) for a in call[0]) for call in mock_print.call_args_list]
        self.assertTrue(any("Opened WhatsApp with draft for Alice" in line for line in printed))

    @patch("builtins.print")
    @patch("flash_executor.subprocess.run")
    def test_cli_whatsapp_missing_message_asks_clarification(self, mock_run, mock_print):
        mock_run.return_value = _make_proc(0)
        import flash_cli
        from flash_aws_brain import FlashAWSBrain

        inputs = [
            {"type": "final", "text": "send a whatsapp message to Alice"},
            {"type": "final", "text": "I am on my way"},  # Clarification answered
            {"type": "final", "text": "yes"},             # Confirmation answered
            {"type": "final", "text": "quit"}
        ]

        def mock_listen():
            for item in inputs:
                yield item
            while True:
                yield {"type": "final", "text": "quit"}

        args = MagicMock()
        args.voice = True
        brain = FlashAWSBrain()
        task_context = TaskContext()

        flash_cli._run_loop(args, mock_listen(), brain, task_context)

        mock_run.assert_called_once()
        printed = [" ".join(str(a) for a in call[0]) for call in mock_print.call_args_list]
        self.assertTrue(any("What message would you like to send to Alice on WhatsApp?" in line for line in printed))
        self.assertTrue(any("Would you like to proceed?" in line for line in printed))
        self.assertTrue(any("Opened WhatsApp with draft for Alice" in line for line in printed))


if __name__ == "__main__":
    unittest.main(verbosity=2)
