import unittest
from unittest.mock import patch
import json
import os
import tempfile
from pathlib import Path

from flash_plan_executor import _create_text_file

class PlanExecutorFileTests(unittest.TestCase):

    def setUp(self):
        self.temp_dir_obj = tempfile.TemporaryDirectory()
        self.temp_dir = Path(self.temp_dir_obj.name)
        
    def tearDown(self):
        self.temp_dir_obj.cleanup()

    def test_create_text_file_success(self):
        with patch('flash_plan_executor.Path.home') as mock_home:
            # We pretend the temp_dir is the user's home directory.
            # _create_text_file uses Path.home() / "Desktop" / "FLASH_AI_Output"
            mock_home.return_value = self.temp_dir
            
            result = _create_text_file("notes.txt", "Hello world!")
            
            sandbox = self.temp_dir / "Desktop" / "FLASH_AI_Output"
            expected_file = sandbox / "notes.txt"
            
            self.assertTrue(result.ok)
            self.assertIn("Created file", result.message)
            self.assertEqual(result.extracted_targets, [str(expected_file)])
            
            self.assertTrue(expected_file.exists())
            self.assertEqual(expected_file.read_text(encoding='utf-8'), "Hello world!")

    def test_create_text_file_duplicate_rejected(self):
        with patch('flash_plan_executor.Path.home') as mock_home:
            mock_home.return_value = self.temp_dir
            
            sandbox = self.temp_dir / "Desktop" / "FLASH_AI_Output"
            sandbox.mkdir(parents=True, exist_ok=True)
            (sandbox / "existing.txt").write_text("old content")
            
            result = _create_text_file("existing.txt", "new content")
            
            self.assertFalse(result.ok)
            self.assertIn("already exists", result.message)
            self.assertEqual((sandbox / "existing.txt").read_text(), "old content") # Not overwritten

    def test_create_text_file_invalid_name(self):
        with patch('flash_plan_executor.Path.home') as mock_home:
            mock_home.return_value = self.temp_dir
            
            result = _create_text_file("../notes.txt", "Hello")
            self.assertFalse(result.ok)
            self.assertIn("Filename must be alphanumeric", result.message)

            result2 = _create_text_file("sub/notes.txt", "Hello")
            self.assertFalse(result2.ok)

    def test_create_text_file_empty_content(self):
        result = _create_text_file("notes.txt", "")
        self.assertFalse(result.ok)
        self.assertIn("empty file", result.message)

    def test_create_text_file_oversized_content(self):
        result = _create_text_file("notes.txt", "A" * (10 * 1024 * 1024 + 1))
        self.assertFalse(result.ok)
        self.assertIn("exceeds 10MB limit", result.message)

    def test_create_text_file_symlinked_sandbox(self):
        with patch('flash_plan_executor.Path.home') as mock_home:
            mock_home.return_value = self.temp_dir
            
            sandbox = self.temp_dir / "Desktop" / "FLASH_AI_Output"
            (self.temp_dir / "Desktop").mkdir(parents=True, exist_ok=True)
            
            # Create a real folder
            real_folder = self.temp_dir / "real"
            real_folder.mkdir()
            
            # Symlink the sandbox to it
            sandbox.symlink_to(real_folder)
            
            result = _create_text_file("notes.txt", "Hello")
            self.assertFalse(result.ok)
            self.assertIn("sandbox directory is a symlink", result.message)

    def test_create_text_file_dir_replacement_race(self):
        with patch('flash_plan_executor.Path.home') as mock_home, \
             patch('pathlib.Path.is_symlink', return_value=False):
            mock_home.return_value = self.temp_dir
            
            sandbox = self.temp_dir / "Desktop" / "FLASH_AI_Output"
            (self.temp_dir / "Desktop").mkdir(parents=True, exist_ok=True)
            real_folder = self.temp_dir / "real2"
            real_folder.mkdir()
            
            # Attacker symlinks it. is_symlink is mocked to return False (simulating TOCTOU bypass).
            sandbox.symlink_to(real_folder)
            
            # However, os.open with O_DIRECTORY | O_NOFOLLOW must still fail natively!
            result = _create_text_file("notes.txt", "Hello")
            self.assertFalse(result.ok)
            self.assertIn("failed to anchor sandbox directory", result.message)

    def test_create_text_file_partial_write_cleanup(self):
        with patch('flash_plan_executor.Path.home') as mock_home, \
             patch('flash_plan_executor.os.fdopen') as mock_fdopen:
            mock_home.return_value = self.temp_dir
            
            # Mock fdopen to throw an exception during writing
            mock_fdopen.side_effect = IOError("Disk full")
            
            result = _create_text_file("fail.txt", "Hello world!")
            
            self.assertFalse(result.ok)
            self.assertIn("Cleaned up partial file", result.message)
            
            # Ensure the file was cleaned up by the except block
            sandbox = self.temp_dir / "Desktop" / "FLASH_AI_Output"
            self.assertFalse((sandbox / "fail.txt").exists())

if __name__ == "__main__":
    unittest.main(verbosity=2)
