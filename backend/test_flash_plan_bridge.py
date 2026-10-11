"""Offline safety tests for the FLASH planner bridge."""

import unittest
from unittest.mock import patch

from flash_plan_bridge import (
    execute_validated_plan,
    validate_plan_for_dry_run,
)
from flash_plan_executor import PlanActionResult


def make_plan(*steps, needs_clarification=False, clarification=""):
    return {
        "steps": list(steps),
        "needs_clarification": needs_clarification,
        "clarification": clarification,
    }


def step(action, target, requires_confirmation=False, details="Test step"):
    return {
        "action": action,
        "target": target,
        "details": details,
        "requires_confirmation": requires_confirmation,
    }


class PlanBridgeSafetyTests(unittest.TestCase):
    def test_allowlisted_app_is_previewed(self):
        plan = make_plan(step("open_app", "Calculator"))
        result = validate_plan_for_dry_run(plan)
        self.assertEqual(len(result), 1)
        self.assertIn("open_app", result[0])

    def test_empty_plan_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "non-empty"):
            validate_plan_for_dry_run(make_plan())

    def test_clarification_request_is_rejected(self):
        plan = make_plan(
            step("open_app", "Calculator"),
            needs_clarification=True,
            clarification="Which app?",
        )
        with self.assertRaisesRegex(ValueError, "clarification"):
            validate_plan_for_dry_run(plan)

    def test_discovered_app_is_accepted_for_dry_run(self):
        from flash_plan_executor import resolve_app
        if resolve_app("Terminal") is None:
            self.skipTest("Terminal app was not discovered on this Mac.")
        result = validate_plan_for_dry_run(
            make_plan(step("open_app", "Terminal"))
        )
        self.assertEqual(len(result), 1)

    def test_unsupported_message_action_is_rejected(self):
        plan = make_plan(step("prepare_message", "WhatsApp", True))
        with self.assertRaisesRegex(ValueError, "unsupported action"):
            validate_plan_for_dry_run(plan)

    def test_mixed_plan_is_rejected_as_a_whole(self):
        plan = make_plan(
            step("open_app", "Calculator"),
            step("prepare_message", "WhatsApp", True),
        )
        with self.assertRaisesRegex(ValueError, "entire plan is rejected"):
            validate_plan_for_dry_run(plan)

    def test_confirmation_required_is_rejected(self):
        plan = make_plan(step("open_app", "Calculator", True))
        with self.assertRaisesRegex(ValueError, "requires confirmation"):
            validate_plan_for_dry_run(plan)

    def test_arbitrary_website_is_rejected_for_dry_run(self):
        plan = make_plan(step("web_search", "example.com"))
        with self.assertRaisesRegex(ValueError, "invalid or unsafe"):
            validate_plan_for_dry_run(plan)

    def test_invalid_plan_type_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "JSON object"):
            validate_plan_for_dry_run([])

    @patch("flash_plan_bridge.execute_step")
    def test_execution_calls_executor_only_after_validation(self, mock_execute):
        mock_execute.return_value = PlanActionResult(True, "mocked success")
        plan = make_plan(step("open_app", "Calculator"))

        result = execute_validated_plan(plan)

        self.assertEqual(result, (True, ["mocked success"], []))
        mock_execute.assert_called_once_with(plan["steps"][0], dry_run=False)

    @patch("flash_plan_bridge.execute_step")
    def test_invalid_mixed_plan_executes_nothing(self, mock_execute):
        plan = make_plan(
            step("open_app", "Calculator"),
            step("prepare_message", "WhatsApp", True),
        )

        with self.assertRaisesRegex(ValueError, "entire plan is rejected"):
            execute_validated_plan(plan)

        mock_execute.assert_not_called()


if __name__ == "__main__":
    unittest.main()
