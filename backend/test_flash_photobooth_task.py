"""Unit tests for Photo Booth task execution, routing, permissions, and verification.

All tests mock subprocess calls and filesystem access — no real photos are taken.
"""
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from flash_executor import execute
from flash_router import route


def _make_proc(returncode: int, stdout: str = "", stderr: str = "") -> MagicMock:
    proc = MagicMock()
    proc.returncode = returncode
    proc.stdout = stdout
    proc.stderr = stderr
    return proc


class PhotoBoothRoutingTests(unittest.TestCase):
    def test_distinguish_open_camera_from_capture(self):
        self.assertEqual(route("open camera").intent, "open_camera")
        self.assertEqual(route("open photo booth").intent, "open_photo_booth")
        self.assertEqual(route("launch camera").intent, "open_camera")

    def test_capture_photo_phrases(self):
        cases = [
            "take a photo",
            "take a picture",
            "capture photo",
            "snap a photo",
            "click a picture",
            "take photo",
        ]
        for phrase in cases:
            with self.subTest(phrase=phrase):
                decision = route(phrase)
                self.assertEqual(decision.intent, "capture_photo")
                self.assertEqual(decision.source, "rule")


class PhotoBoothExecutorTests(unittest.TestCase):
    @patch("flash_executor.subprocess.run")
    def test_open_camera_does_not_claim_capture(self, mock_run):
        mock_run.return_value = _make_proc(0)
        result = execute("open_camera")
        self.assertTrue(result.ok)
        self.assertEqual(result.message, "Done: open_camera")
        # Ensure only open -a Photo Booth was called, not osascript
        args, _ = mock_run.call_args
        self.assertEqual(args[0], ["open", "-a", "Photo Booth"])

    @patch("flash_executor.subprocess.run")
    def test_capture_photo_accessibility_permission_denied(self, mock_run):
        # First call launches Photo Booth, second call runs osascript System Events
        open_proc = _make_proc(0)
        shutter_proc = _make_proc(1, stderr="System Events got an error: osascript is not allowed assistive access. (-1719)")
        mock_run.side_effect = [open_proc, shutter_proc]

        result = execute("capture_photo")
        self.assertFalse(result.ok)
        self.assertIn("Accessibility permissions", result.message)
        self.assertIn("(-1719)", result.message)

    @patch("flash_executor.time.sleep")
    @patch("flash_executor.Path.is_dir")
    @patch("flash_executor.subprocess.run")
    def test_capture_photo_unverified_library(self, mock_run, mock_is_dir, mock_sleep):
        # Shutter succeeds, but library folder does not exist or has no new photos
        mock_is_dir.return_value = False
        mock_run.side_effect = [_make_proc(0), _make_proc(0)]

        result = execute("capture_photo")
        self.assertTrue(result.ok)
        self.assertIn("Photo Booth shutter triggered", result.message)
        self.assertIn("could not be independently verified", result.message)

    @patch("flash_executor.time.sleep")
    @patch("flash_executor.Path.iterdir")
    @patch("flash_executor.Path.is_dir")
    @patch("flash_executor.subprocess.run")
    def test_capture_photo_verified_file(self, mock_run, mock_is_dir, mock_iterdir, mock_sleep):
        mock_is_dir.return_value = True
        mock_run.side_effect = [_make_proc(0), _make_proc(0)]

        file1 = MagicMock(spec=Path)
        file1.name = "Photo 1.jpg"
        file1.is_file.return_value = True

        file2 = MagicMock(spec=Path)
        file2.name = "Photo 2.jpg"
        file2.is_file.return_value = True

        # Before shutter: file1 only; after shutter: file1 and file2
        mock_iterdir.side_effect = [[file1], [file1, file2]]

        result = execute("capture_photo")
        self.assertTrue(result.ok)
        self.assertIn("Photo captured in Photo Booth: Photo 2.jpg", result.message)

    @patch("flash_executor.subprocess.run")
    def test_capture_photo_launch_failure(self, mock_run):
        mock_run.return_value = _make_proc(1, stderr="Unable to find application")
        result = execute("capture_photo")
        self.assertFalse(result.ok)
        self.assertIn("Could not open Photo Booth", result.message)


if __name__ == "__main__":
    unittest.main(verbosity=2)
