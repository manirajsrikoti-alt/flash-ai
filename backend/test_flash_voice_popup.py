"""Tests for FlashVoicePopup in flash_voice_popup.py.

All tests operate in headless mode or mocked Tkinter without opening real display windows.
"""

import unittest
from unittest.mock import MagicMock, patch

from flash_voice_popup import FlashVoicePopup


class FlashVoicePopupStateTests(unittest.TestCase):
    """Test state management, queue updates, and headless operations."""

    def test_headless_initialization(self):
        popup = FlashVoicePopup(headless=True)
        self.assertTrue(popup.headless)
        self.assertEqual(popup.current_state, "idle")
        self.assertFalse(popup.is_dismissed())

    def test_state_transitions(self):
        popup = FlashVoicePopup(headless=True)
        popup.set_state("listening")
        self.assertEqual(popup.current_state, "listening")
        
        popup.set_state("processing")
        self.assertEqual(popup.current_state, "processing")
        
        popup.set_state("speaking")
        self.assertEqual(popup.current_state, "speaking")

    def test_transcript_update(self):
        popup = FlashVoicePopup(headless=True)
        popup.set_transcript("open Notes")
        self.assertEqual(popup.current_transcript, "open Notes")

    def test_response_update(self):
        popup = FlashVoicePopup(headless=True)
        popup.set_response("Opened Apple Notes.")
        self.assertEqual(popup.current_response, "Opened Apple Notes.")

    def test_dismiss_callback(self):
        mock_callback = MagicMock()
        popup = FlashVoicePopup(headless=True, on_dismiss=mock_callback)
        popup._handle_ui_dismiss()
        
        self.assertTrue(popup.is_dismissed())
        mock_callback.assert_called_once()

    def test_request_close(self):
        popup = FlashVoicePopup(headless=True)
        popup.request_close()
        self.assertFalse(popup._command_queue.empty())
        cmd, val = popup._command_queue.get_nowait()
        self.assertEqual(cmd, "close")

    def test_queue_processing_headless(self):
        popup = FlashVoicePopup(headless=True)
        popup.set_state("listening")
        popup.set_transcript("hello")
        popup.set_response("world")
        
        popup._process_queue()
        self.assertEqual(popup.current_state, "listening")
        self.assertEqual(popup.current_transcript, "hello")
        self.assertEqual(popup.current_response, "world")

    @patch("flash_voice_popup.tk")
    def test_init_window_failure_falls_back_to_headless(self, mock_tk):
        mock_tk.Tk.side_effect = Exception("Display connection failed")
        popup = FlashVoicePopup(headless=False)
        self.assertTrue(popup.headless)
        self.assertIsNone(popup.root)
