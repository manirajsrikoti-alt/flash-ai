import unittest
from unittest.mock import patch, MagicMock

from flash_plan_executor import normalize_website_url, _open_website, _search_web

class PlanExecutorWebsiteTests(unittest.TestCase):
    def test_normalize_website_url_approved(self):
        cases = {
            "google": "https://www.google.com",
            "youtube": "https://www.youtube.com",
            "centle.in": "https://centle.in",
            "https://www.wikipedia.org": "https://www.wikipedia.org",
            "github.com": "https://github.com",
        }
        for site, expected in cases.items():
            with self.subTest(site=site):
                self.assertEqual(normalize_website_url(site), expected)

    def test_normalize_website_url_rejected(self):
        cases = [
            "evil.com", # unapproved domain
            "https://evil.example", # unapproved domain
            "https://google.com:badport", # malformed port
            "ftp://google.com", # unsupported scheme
            "https://user:pass@google.com", # embedded credentials
            "https://google.com.evil.com", # deceptive hostname
            "https://evil.com/google.com", # deceptive hostname
            "file:///etc/passwd", # local file
            "localhost", # local destination
            "http://test.localhost", # local destination
            "https:////google.com", # double slash domain prefix
        ]
        for site in cases:
            with self.subTest(site=site):
                self.assertIsNone(normalize_website_url(site))

    @patch("flash_plan_executor.subprocess.run")
    def test_open_website_browser_command(self, mocked_run):
        mocked_run.return_value = MagicMock(returncode=0)
        
        result = _open_website("centle.in")
        self.assertTrue(result.ok)
        self.assertIn("default browser", result.message)
        
        args, kwargs = mocked_run.call_args
        self.assertEqual(args[0], ["open", "https://centle.in"])
        self.assertEqual(kwargs["timeout"], 10)

    @patch("flash_plan_executor.subprocess.run")
    def test_search_web_browser_command(self, mocked_run):
        mocked_run.return_value = MagicMock(returncode=0)
        
        result = _search_web("google", "test query")
        self.assertTrue(result.ok)
        
        args, _ = mocked_run.call_args
        self.assertEqual(args[0], ["open", "https://www.google.com/search?q=test+query"])

if __name__ == "__main__":
    unittest.main(verbosity=2)
