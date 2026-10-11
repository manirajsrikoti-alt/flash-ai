import unittest
from unittest.mock import patch, MagicMock
import json

from flash_plan_executor import _read_chrome_tabs

class PlanExecutorChromeTests(unittest.TestCase):
    @patch("flash_plan_executor.subprocess.run")
    def test_read_chrome_tabs_success(self, mocked_run):
        mocked_proc = MagicMock()
        mocked_proc.returncode = 0
        mocked_proc.stdout = json.dumps({
            "tabs": [
                {"title": "GitHub", "url": "https://github.com"},
                {"title": "Google", "url": "https://google.com"}
            ]
        })
        mocked_run.return_value = mocked_proc

        result = _read_chrome_tabs()
        
        self.assertTrue(result.ok)
        self.assertIn("Read 2 tabs", result.message)
        self.assertEqual(result.extracted_targets, ["https://github.com", "https://google.com"])
        
        args, kwargs = mocked_run.call_args
        self.assertEqual(args[0][0], "osascript")
        self.assertEqual(args[0][1], "-l")
        self.assertEqual(args[0][2], "JavaScript")

    @patch("flash_plan_executor.subprocess.run")
    def test_read_chrome_tabs_not_running(self, mocked_run):
        mocked_proc = MagicMock()
        mocked_proc.returncode = 0
        mocked_proc.stdout = json.dumps({"error": "Chrome is not running."})
        mocked_run.return_value = mocked_proc

        result = _read_chrome_tabs()
        
        self.assertFalse(result.ok)
        self.assertIn("Chrome is not running", result.message)
        self.assertEqual(result.extracted_targets, [])

    @patch("flash_plan_executor.subprocess.run")
    def test_read_chrome_tabs_permission_denied(self, mocked_run):
        mocked_proc = MagicMock()
        mocked_proc.returncode = 1
        mocked_proc.stdout = ""
        mocked_run.return_value = mocked_proc

        result = _read_chrome_tabs()
        
        self.assertFalse(result.ok)
        self.assertIn("Privacy & Security", result.message)

if __name__ == "__main__":
    unittest.main(verbosity=2)
