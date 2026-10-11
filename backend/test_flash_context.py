import unittest
from unittest.mock import patch, MagicMock
from flash_context import TaskContext, ActionRecord

class TestTaskContext(unittest.TestCase):
    def setUp(self):
        self.context = TaskContext(max_history=3)

    def test_add_and_update_action(self):
        record = self.context.add_action("open calculator", "open_calculator", "calculator")
        self.assertEqual(record.status, "pending")
        self.assertEqual(record.intent, "open_calculator")
        self.assertEqual(len(self.context.actions), 1)

        self.context.update_action(record, "running")
        self.assertEqual(record.status, "running")

        self.context.update_action(record, "succeeded", "Opened calculator")
        self.assertEqual(record.status, "succeeded")
        self.assertEqual(record.result_message, "Opened calculator")

    def test_max_history_enforced(self):
        for i in range(5):
            self.context.add_action(f"cmd {i}", "intent", "target")
        self.assertEqual(len(self.context.actions), 3)
        self.assertEqual(self.context.actions[-1].instruction, "cmd 4")
        self.assertEqual(self.context.actions[0].instruction, "cmd 2")

    def test_resolve_reference_it(self):
        # No recent successful action
        self.assertEqual(self.context.resolve_reference("close it"), ("close it", "missing_target"))

        # Add failed action
        rec1 = self.context.add_action("open broken", "open_app", "broken")
        self.context.update_action(rec1, "failed")
        self.assertEqual(self.context.resolve_reference("close it"), ("close it", "missing_target"))

        # Add successful action
        rec2 = self.context.add_action("open chrome", "open_chrome", "Google Chrome")
        self.context.update_action(rec2, "succeeded")
        self.assertEqual(self.context.resolve_reference("close it"), ("close Google Chrome", None))

        # Doesn't resolve if 'it' is not in the text
        self.assertEqual(self.context.resolve_reference("close chrome"), ("close chrome", None))

    def test_resolve_reference_multi(self):
        rec = self.context.add_action("read tabs", "read_chrome_tabs", ["url1", "url2"])
        self.context.update_action(rec, "succeeded")
        
        self.assertEqual(self.context.resolve_reference("close it"), ("close it", "ambiguous"))
        self.assertEqual(self.context.resolve_reference("close the first one"), ("close url1", None))
        self.assertEqual(self.context.resolve_reference("close the second tab"), ("close url2", None))

    def test_reset(self):
        self.context.add_action("cmd", "intent")
        self.context.reset()
        self.assertEqual(len(self.context.actions), 0)

if __name__ == "__main__":
    unittest.main()
