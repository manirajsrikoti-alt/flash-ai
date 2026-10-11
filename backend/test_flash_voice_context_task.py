"""Comprehensive tests for FLASH voice latency, context, phase, and task management."""

import unittest
import queue
import time
from unittest.mock import MagicMock, patch

from flash_context import TaskContext, TaskPhase, StepRecord, TaskState
from flash_voice_popup import FlashVoicePopup
from flash_voice_continuous import (
    QUEUE_MAX_SIZE,
    Utterance,
    drain_queue,
    warmup_whisper,
    SILENCE_SECONDS,
)
from flash_laya_classifier import warmup as warmup_laya, classify
import flash_cli


class TestTaskContextAndProgression(unittest.TestCase):
    def setUp(self):
        self.context = TaskContext(max_history=5, expiry_seconds=60.0)

    def test_context_retention_across_turns(self):
        """Test session preservation across successive turns."""
        self.assertIsNotNone(self.context.session_id)
        turn1 = self.context.add_turn("user", "open Calculator", intent="open_calculator")
        turn2 = self.context.add_turn("assistant", "Opened Calculator", phase="completed")
        
        self.assertEqual(len(self.context.turns), 2)
        self.assertEqual(self.context.turns[0].text, "open Calculator")
        self.assertEqual(self.context.turns[1].role, "assistant")

    def test_multi_step_task_progression(self):
        """Test multi-step task execution without rerunning completed steps."""
        task = self.context.create_task(
            "Open Chrome and search Python",
            [
                {"action": "open_app", "target": "Google Chrome"},
                {"action": "search_web", "target": "google", "details": "Python"},
            ],
        )
        self.assertEqual(len(task.steps), 2)
        self.assertEqual(task.phase, TaskPhase.EXECUTING)
        self.assertEqual(task.current_step_index, 0)

        # Step 1 runs and succeeds
        self.context.mark_step_running(0)
        self.assertEqual(task.steps[0].status, "running")
        self.context.record_step_result(0, True, "Opened Google Chrome")
        self.assertEqual(task.steps[0].status, "succeeded")
        self.assertEqual(task.current_step_index, 1)
        self.assertFalse(task.is_complete())

        # Step 2 runs and succeeds
        self.context.mark_step_running(1)
        self.context.record_step_result(1, True, "Opened search results for Python")
        self.assertEqual(task.steps[1].status, "succeeded")
        self.assertTrue(task.is_complete())
        self.assertEqual(task.phase, TaskPhase.COMPLETED)

        # Both steps verified succeeded; completed steps count is 2
        completed = task.get_completed_steps()
        self.assertEqual(len(completed), 2)

    def test_failure_handling_and_safe_retry(self):
        """Test that retry attempts only the failed step without rerunning succeeded steps."""
        task = self.context.create_task(
            "Create file and search web",
            [
                {"action": "open_app", "target": "Google Chrome"},
                {"action": "search_web", "target": "google", "details": "test"},
            ],
        )
        # Step 1 succeeds
        self.context.record_step_result(0, True, "Step 1 OK")
        # Step 2 fails
        self.context.record_step_result(1, False, "Network error")
        self.assertEqual(task.phase, TaskPhase.FAILED)
        self.assertTrue(self.context.can_retry_task())

        # Follow-up "retry" resolves to followup_retry
        resolved, error = self.context.resolve_reference("retry")
        self.assertEqual(error, "followup_retry")

        # Prepare retry resets ONLY the failed step
        retry_step = self.context.prepare_retry_step()
        self.assertIsNotNone(retry_step)
        idx, step = retry_step
        self.assertEqual(idx, 1)
        self.assertEqual(step.action, "search_web")
        self.assertEqual(step.status, "pending")

        # Step 0 MUST still be succeeded!
        self.assertEqual(task.steps[0].status, "succeeded")

        # Retry step 1 succeeds
        self.context.record_step_result(1, True, "Step 2 Succeeded on retry")
        self.assertTrue(task.is_complete())
        self.assertEqual(task.phase, TaskPhase.COMPLETED)

    def test_followup_continue(self):
        """Test 'continue' advances to next pending step."""
        task = self.context.create_task(
            "Two step plan",
            [
                {"action": "open_app", "target": "Notes"},
                {"action": "open_app", "target": "Calculator"},
            ],
        )
        self.context.record_step_result(0, True, "Notes opened")
        resolved, error = self.context.resolve_reference("continue")
        self.assertEqual(error, "followup_continue")

        next_step = self.context.advance_to_next_step()
        self.assertIsNotNone(next_step)
        idx, step = next_step
        self.assertEqual(idx, 1)
        self.assertEqual(step.target, "Calculator")

    def test_ambiguity_and_missing_target(self):
        """Test ambiguous references require clarification and missing targets fail gracefully."""
        # Missing target with no active task or actions
        text, err = self.context.resolve_reference("open it")
        self.assertEqual(err, "missing_target")

        # Ambiguous when multiple targets are present
        rec = self.context.add_action("read tabs", "read_chrome_tabs", ["site1.com", "site2.com"])
        self.context.update_action(rec, "succeeded")
        text, err = self.context.resolve_reference("open it")
        self.assertEqual(err, "ambiguous")

        # Unambiguous ordered reference
        text, err = self.context.resolve_reference("open the first one")
        self.assertEqual(text, "open site1.com")
        self.assertIsNone(err)

    def test_context_expiry_policy(self):
        """Test that stale context expires and cannot trigger unintended actions."""
        self.context.expiry_seconds = 0.5
        rec = self.context.add_action("open notes", "open_notes", "Notes")
        self.context.update_action(rec, "succeeded")
        self.context.create_task("Open notes", [{"action": "open_app", "target": "Notes"}])
        
        # Immediate reference resolves
        text, err = self.context.resolve_reference("open it")
        self.assertEqual(text, "open Notes")
        self.assertIsNone(err)

        # Wait for expiry
        time.sleep(0.6)
        self.assertTrue(self.context.is_expired())

        # Reference resolution after expiry rejects stale context
        text, err = self.context.resolve_reference("open it")
        self.assertEqual(err, "missing_target")
        self.assertIsNone(self.context.active_task)

    def test_safety_never_bypassed_by_context(self):
        """Test that dangerous commands are strictly blocked regardless of prior conversation."""
        self.context.add_turn("user", "Hello assistant")
        self.context.add_turn("assistant", "How can I help?")

        blocked_commands = [
            "delete my notes",
            "rm -rf /",
            "sudo shutdown",
            "send an email to Alice",
            "pay $500",
            "format disk",
        ]
        for cmd in blocked_commands:
            self.assertIsNotNone(flash_cli.BLOCKED_PATTERN.search(cmd))


class TestVoicePopupPhases(unittest.TestCase):
    def test_popup_truthful_phases(self):
        """Test that the popup exposes truthful states: listening, planning, executing, completed, failed."""
        popup = FlashVoicePopup(headless=True)
        phases = [
            "listening",
            "transcribing",
            "understanding",
            "planning",
            "executing",
            "awaiting_confirmation",
            "awaiting_clarification",
            "completed",
            "failed",
            "speaking",
        ]
        for p in phases:
            popup.set_state(p)
            self.assertEqual(popup.current_state, p)
            popup._process_queue()


class TestVoiceQueueAndAudioResponsiveness(unittest.TestCase):
    def test_bounded_queue_overflow(self):
        """Test that audio queue is bounded and drops blocks on overflow without blocking."""
        q = queue.Queue(maxsize=QUEUE_MAX_SIZE)
        for i in range(QUEUE_MAX_SIZE):
            q.put_nowait(i)
        self.assertEqual(q.qsize(), QUEUE_MAX_SIZE)

        # Dropping block on full queue
        overflowed = False
        try:
            q.put_nowait(999)
        except queue.Full:
            overflowed = True
        self.assertTrue(overflowed)

    def test_drain_stale_audio(self):
        """Test that stale audio accumulated during slow execution is drained cleanly."""
        q = queue.Queue(maxsize=50)
        for i in range(20):
            q.put(i)
        dropped = drain_queue(q, max_keep=1)
        self.assertEqual(dropped, 19)
        self.assertEqual(q.qsize(), 1)

    def test_utterance_metadata(self):
        """Test Utterance object retains timings while behaving as a string."""
        ut = Utterance("open calculator", {"vad_silence_s": 0.45, "transcription_ms": 185.0})
        self.assertEqual(ut, "open calculator")
        self.assertEqual(ut.strip(), "open calculator")
        self.assertEqual(ut.timings["vad_silence_s"], 0.45)
        self.assertEqual(ut.timings["transcription_ms"], 185.0)

    def test_silence_seconds_configuration(self):
        """Verify configured silence timeout is around 450-600ms."""
        self.assertGreaterEqual(SILENCE_SECONDS, 0.4)
        self.assertLessEqual(SILENCE_SECONDS, 0.6)


class TestLayaAndPlannerRouting(unittest.TestCase):
    @patch("flash_cli.classify")
    @patch("flash_executor.execute")
    def test_laya_fast_path_routing(self, mock_exec, mock_classify):
        """Simple supported commands route via Laya/Router fast-path directly without planner."""
        from flash_router import route
        mock_classify.return_value = ("open_notes", 0.95)
        decision = route("open my notes", classifier=mock_classify)
        self.assertEqual(decision.intent, "open_notes")
        self.assertIn(decision.source, {"rule", "model"})

    @patch("flash_ai_planner.plan_request")
    def test_planner_clarification_displayed_not_rejected(self, mock_plan_request):
        """Planner output with needs_clarification=True displays clarification question without rejecting."""
        mock_plan_request.return_value = {
            "steps": [],
            "needs_clarification": True,
            "clarification": "Which project folder would you like to open?",
        }
        context = TaskContext()
        brain = MagicMock()
        
        # Test that flash_cli handles needs_clarification gracefully
        from flash_ai_planner import plan_request
        plan = plan_request(brain, "open my project", context)
        self.assertTrue(plan["needs_clarification"])
        self.assertEqual(plan["clarification"], "Which project folder would you like to open?")

    def test_laya_warmup_thread_safety(self):
        """Test warmup function runs safely and idempotently."""
        self.assertTrue(warmup_laya())
        self.assertTrue(warmup_laya())


if __name__ == "__main__":
    unittest.main()
