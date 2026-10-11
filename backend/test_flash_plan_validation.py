"""Offline tests for FLASH plan validation. No AWS calls or Mac actions."""

import unittest
import json

from flash_ai_planner import extract_json


def make_plan(action, confirmation=False):
    return {
        "steps": [{
            "action": action,
            "target": "",
            "details": "Test step",
            "requires_confirmation": confirmation,
        }],
        "needs_clarification": False,
        "clarification": "",
    }


class PlanValidationTests(unittest.TestCase):

    def test_recipient_identification_forces_confirmation(self):
        plan = extract_json(json.dumps(make_plan("identify_recipients", False)))
        self.assertTrue(plan["steps"][0]["requires_confirmation"])

    def test_message_preparation_forces_confirmation(self):
        plan = extract_json(json.dumps(make_plan("prepare_message", False)))
        self.assertTrue(plan["steps"][0]["requires_confirmation"])

    def test_confirmation_action_forces_confirmation(self):
        plan = extract_json(json.dumps(make_plan("request_confirmation", False)))
        self.assertTrue(plan["steps"][0]["requires_confirmation"])

    def test_open_app_can_remain_without_confirmation(self):
        plan = extract_json(json.dumps(make_plan("open_app", False)))
        self.assertFalse(plan["steps"][0]["requires_confirmation"])

    def test_unknown_action_is_rejected(self):
        with self.assertRaises(ValueError):
            extract_json(json.dumps(make_plan("send_message", True)))

    def test_missing_confirmation_flag_is_rejected(self):
        plan = make_plan("open_app")
        del plan["steps"][0]["requires_confirmation"]
        with self.assertRaises(ValueError):
            extract_json(json.dumps(plan))

    def test_invalid_json_is_rejected(self):
        with self.assertRaises(ValueError):
            extract_json("{not valid JSON")

    def test_non_object_response_is_rejected(self):
        with self.assertRaises(ValueError):
            extract_json("[]")


if __name__ == "__main__":
    unittest.main(verbosity=2)
