import unittest
from unittest.mock import patch, MagicMock

from flash_router import route
from flash_executor import execute, _validated_url

class WebsiteRoutingTests(unittest.TestCase):
    def test_supported_website_aliases(self):
        cases = {
            "open centle.in": ("open_website", "centle.in"),
            "open google": ("open_website", "google.com"),
            "open wikipedia": ("open_website", "wikipedia.org"),
            "visit centle.in": ("open_website", "centle.in"),
            "go to centle.in": ("open_website", "centle.in"),
            "browse to centle.in": ("open_website", "centle.in"),
            "take me to centle.in": ("open_website", "centle.in"),
            "go to youtube": ("open_youtube", "youtube.com"),
            "open youtube": ("open_youtube", "youtube.com"),
        }
        for phrase, (expected_intent, expected_target) in cases.items():
            with self.subTest(phrase=phrase):
                decision = route(phrase)
                self.assertEqual(decision.intent, expected_intent)
                self.assertEqual(decision.target, expected_target)
                self.assertEqual(decision.source, "rule")

    def test_explicit_urls(self):
        cases = {
            "open https://www.google.com": ("open_website", "https://www.google.com"),
            "go to https://centle.in": ("open_website", "https://centle.in"),
            "visit http://wikipedia.org": ("open_website", "http://wikipedia.org"),
        }
        for phrase, (expected_intent, expected_target) in cases.items():
            with self.subTest(phrase=phrase):
                decision = route(phrase)
                self.assertEqual(decision.intent, expected_intent)
                self.assertEqual(decision.target, expected_target)
                self.assertEqual(decision.source, "rule")

    def test_rejections_and_unsupported(self):
        cases = [
            "open evil.com",
            "open https://evil.example",
            "open ftp://google.com",
            "go to file:///etc/passwd",
            "open [https://google.com](https://google.com)", 
            "open [centle.in](https://evil.com)",
            "visit https://google.com.evil.com", 
            "go to https://evil.com/google.com",
        ]
        for phrase in cases:
            with self.subTest(phrase=phrase):
                decision = route(phrase)
                self.assertEqual(decision.intent, "unknown")

    def test_web_search(self):
        cases = {
            "search for python tutorials": "python tutorials",
            "search the web for artificial intelligence": "artificial intelligence",
            "look up recipe for pie": "recipe for pie",
            "google flash ai": "flash ai",
        }
        for phrase, expected_target in cases.items():
            with self.subTest(phrase=phrase):
                decision = route(phrase)
                self.assertEqual(decision.intent, "web_search")
                self.assertEqual(decision.target, expected_target)


class WebsiteExecutorTests(unittest.TestCase):
    @patch("flash_executor.subprocess.run")
    def test_open_website_execution(self, mocked_run):
        mocked_run.return_value = MagicMock(returncode=0)
        
        result = execute("open_website", "centle.in")
        self.assertTrue(result.ok)
        args, kwargs = mocked_run.call_args
        self.assertEqual(args[0], ["open", "https://centle.in"])
        self.assertEqual(kwargs["timeout"], 10)

    @patch("flash_executor.subprocess.run")
    def test_web_search_execution(self, mocked_run):
        mocked_run.return_value = MagicMock(returncode=0)
        
        result = execute("web_search", "python tutorials")
        self.assertTrue(result.ok)
        args, _ = mocked_run.call_args
        self.assertEqual(args[0], ["open", "https://www.google.com/search?q=python+tutorials"])

    def test_validated_url_rejections(self):
        self.assertIsNone(_validated_url("ftp://google.com"))
        self.assertIsNone(_validated_url("file:///etc/passwd"))
        self.assertIsNone(_validated_url("https://user:pass@google.com"))
        self.assertIsNone(_validated_url("https://google.com:badport"))
        self.assertIsNone(_validated_url("google.com evil"))

if __name__ == "__main__":
    unittest.main(verbosity=2)
