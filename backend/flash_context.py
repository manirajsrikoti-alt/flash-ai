"""FLASH AI task context, phase, and structured session system."""

import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional, Any


class TaskPhase:
    IDLE = "idle"
    LISTENING = "listening"
    UNDERSTANDING = "understanding"
    PLANNING = "planning"
    EXECUTING = "executing"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    AWAITING_CLARIFICATION = "awaiting_clarification"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class ConversationTurn:
    role: str  # "user" or "assistant"
    text: str
    timestamp: float = field(default_factory=time.time)
    intent: Optional[str] = None
    phase: Optional[str] = None


@dataclass
class StepRecord:
    action: str
    target: str
    details: str = ""
    requires_confirmation: bool = False
    status: str = "pending"  # "pending", "running", "succeeded", "failed", "cancelled"
    result_message: Optional[str] = None
    extracted_targets: list[str] = field(default_factory=list)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None


@dataclass
class TaskState:
    task_id: str
    goal: str
    phase: str = TaskPhase.PLANNING
    steps: list[StepRecord] = field(default_factory=list)
    current_step_index: int = 0
    required_confirmation: Optional[dict] = None
    clarification_question: Optional[str] = None
    last_result: Optional[str] = None
    last_error: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def is_complete(self) -> bool:
        return bool(self.steps and all(s.status == "succeeded" for s in self.steps))

    def get_pending_step(self) -> Optional[StepRecord]:
        for s in self.steps:
            if s.status in ("pending", "failed"):
                return s
        return None

    def get_completed_steps(self) -> list[StepRecord]:
        return [s for s in self.steps if s.status == "succeeded"]


@dataclass
class ActionRecord:
    instruction: str
    intent: str
    target: Optional[str | list[str]]
    status: str  # "pending", "running", "succeeded", "failed", "cancelled"
    result_message: Optional[str]
    timestamp: float


class TaskContext:
    def __init__(
        self,
        max_history: int = 20,
        expiry_seconds: float = 180.0,
        session_id: Optional[str] = None,
    ):
        self.session_id: str = session_id or str(uuid.uuid4())
        self.max_history = max_history
        self.expiry_seconds = expiry_seconds

        # Structured state
        self.turns: list[ConversationTurn] = []
        self.active_task: Optional[TaskState] = None
        self.completed_tasks: list[TaskState] = []

        # Legacy backward-compatible attributes
        self.actions: list[ActionRecord] = []
        self.current_goal: Optional[str] = None

        self.created_at: float = time.time()
        self.updated_at: float = time.time()

        # Input deduplication state
        self.last_text: Optional[str] = None
        self.last_text_time: float = 0.0

    def touch(self):
        """Update last modified timestamp."""
        self.updated_at = time.time()

    def is_expired(self, current_time: Optional[float] = None) -> bool:
        now = current_time if current_time is not None else time.time()
        return (now - self.updated_at) > self.expiry_seconds

    def check_and_apply_expiry(self, current_time: Optional[float] = None) -> bool:
        """Invalidate stale context when expiry policy triggers."""
        if self.is_expired(current_time):
            if self.active_task:
                self.active_task.phase = TaskPhase.FAILED
                self.active_task.last_error = "Task context expired due to inactivity."
                self.completed_tasks.append(self.active_task)
                self.active_task = None
            self.actions.clear()
            self.current_goal = None
            self.touch()
            return True
        return False

    def add_turn(
        self,
        role: str,
        text: str,
        intent: Optional[str] = None,
        phase: Optional[str] = None,
    ) -> ConversationTurn:
        self.touch()
        turn = ConversationTurn(
            role=role,
            text=text,
            timestamp=time.time(),
            intent=intent,
            phase=phase,
        )
        self.turns.append(turn)
        if len(self.turns) > self.max_history * 2:
            self.turns.pop(0)
        return turn

    def create_task(
        self,
        goal: str,
        steps: Optional[list[dict]] = None,
    ) -> TaskState:
        """Create a new active task with structured steps."""
        self.touch()
        task_id = str(uuid.uuid4())[:8]
        step_records = []
        if steps:
            for s in steps:
                step_records.append(
                    StepRecord(
                        action=s.get("action", ""),
                        target=s.get("target", ""),
                        details=s.get("details", ""),
                        requires_confirmation=s.get("requires_confirmation", False),
                        status="pending",
                    )
                )

        task = TaskState(
            task_id=task_id,
            goal=goal,
            phase=TaskPhase.PLANNING if not step_records else TaskPhase.EXECUTING,
            steps=step_records,
            created_at=time.time(),
            updated_at=time.time(),
        )
        self.active_task = task
        self.current_goal = goal
        return task

    def set_task_phase(
        self,
        phase: str,
        error: Optional[str] = None,
        result: Optional[str] = None,
    ):
        """Update phase of the active task."""
        self.touch()
        if self.active_task:
            self.active_task.phase = phase
            self.active_task.updated_at = time.time()
            if error is not None:
                self.active_task.last_error = error
            if result is not None:
                self.active_task.last_result = result
            if phase == TaskPhase.COMPLETED:
                self.completed_tasks.append(self.active_task)

    def mark_step_running(self, index: int):
        self.touch()
        if self.active_task and 0 <= index < len(self.active_task.steps):
            step = self.active_task.steps[index]
            step.status = "running"
            step.started_at = time.time()
            self.active_task.current_step_index = index
            self.active_task.phase = TaskPhase.EXECUTING

    def record_step_result(
        self,
        index: int,
        ok: bool,
        message: str,
        extracted_targets: Optional[list[str]] = None,
    ):
        """Record outcome strictly verified by executor."""
        self.touch()
        if not self.active_task or not (0 <= index < len(self.active_task.steps)):
            return
        step = self.active_task.steps[index]
        step.completed_at = time.time()
        step.result_message = message
        if extracted_targets:
            step.extracted_targets = extracted_targets

        if ok:
            step.status = "succeeded"
            self.active_task.last_result = message
            if all(s.status == "succeeded" for s in self.active_task.steps):
                self.active_task.phase = TaskPhase.COMPLETED
            else:
                self.active_task.current_step_index = index + 1
        else:
            step.status = "failed"
            self.active_task.last_error = message
            self.active_task.phase = TaskPhase.FAILED

    def can_retry_task(self) -> bool:
        if not self.active_task:
            return False
        return any(s.status == "failed" for s in self.active_task.steps)

    def prepare_retry_step(self) -> Optional[tuple[int, StepRecord]]:
        """Find the failed step and reset status for retry without rerunning succeeded steps."""
        self.touch()
        if not self.active_task:
            return None
        for i, s in enumerate(self.active_task.steps):
            if s.status == "failed":
                s.status = "pending"
                s.result_message = None
                self.active_task.current_step_index = i
                self.active_task.phase = TaskPhase.EXECUTING
                self.active_task.last_error = None
                return (i, s)
        return None

    def advance_to_next_step(self) -> Optional[tuple[int, StepRecord]]:
        """Get the next pending step in the active task."""
        self.touch()
        if not self.active_task:
            return None
        for i, s in enumerate(self.active_task.steps):
            if s.status == "pending":
                self.active_task.current_step_index = i
                self.active_task.phase = TaskPhase.EXECUTING
                return (i, s)
        return None

    def reset(self):
        self.actions.clear()
        self.turns.clear()
        self.active_task = None
        self.completed_tasks.clear()
        self.current_goal = None
        self.last_text = None
        self.last_text_time = 0.0
        self.touch()

    # --- Legacy methods preserved for 100% backward compatibility ---

    def add_action(
        self,
        instruction: str,
        intent: str,
        target: Optional[str | list[str]] = None,
    ) -> ActionRecord:
        self.touch()
        record = ActionRecord(
            instruction=instruction,
            intent=intent,
            target=target,
            status="pending",
            result_message=None,
            timestamp=time.time(),
        )
        self.actions.append(record)
        if len(self.actions) > self.max_history:
            self.actions.pop(0)
        return record

    def update_action(
        self,
        record: ActionRecord,
        status: str,
        result_message: Optional[str] = None,
        new_target: Optional[str | list[str]] = None,
    ):
        self.touch()
        record.status = status
        if result_message is not None:
            record.result_message = result_message
        if new_target is not None:
            record.target = new_target
        record.timestamp = time.time()

    def get_recent_successful_action(self) -> Optional[ActionRecord]:
        for record in reversed(self.actions):
            if record.status == "succeeded":
                return record
        return None

    def resolve_reference(self, text: str) -> tuple[str, Optional[str]]:
        """Resolve ambiguous references ('it', 'first one', 'retry', 'continue').
        
        Returns (resolved_text, error_message).
        - If ambiguous: (text, 'ambiguous')
        - If missing evidence or stale: (text, 'missing_target')
        - If follow-up action: (resolved_text, None or 'followup_...')
        - If resolved reference: (substituted_text, None)
        - If no reference: (text, None)
        """
        # Expiry check: prevent stale context from triggering unintended actions
        if self.is_expired():
            self.check_and_apply_expiry()

        words = text.lower().split()
        normalized = " ".join(words)

        # Check follow-up commands first
        if normalized in {"retry", "try again", "retry the step", "retry failed step"}:
            if not self.active_task or not self.can_retry_task():
                return text, "missing_target"
            return text, "followup_retry"

        if normalized in {"continue", "next step", "do the next step", "proceed"}:
            if not self.active_task or not self.active_task.get_pending_step():
                return text, "missing_target"
            return text, "followup_continue"

        has_it = "it" in words
        has_first = "first" in words and ("one" in words or "tab" in words or "result" in words)
        has_second = "second" in words and ("one" in words or "tab" in words or "result" in words)

        if not (has_it or has_first or has_second):
            return text, None

        # Resolve targets from recent successful action or active task's completed steps
        targets = []
        recent = self.get_recent_successful_action()
        if recent and recent.target:
            targets = recent.target if isinstance(recent.target, list) else [recent.target]
        elif self.active_task:
            completed = self.active_task.get_completed_steps()
            if completed:
                for c in completed:
                    if c.extracted_targets:
                        targets.extend(c.extracted_targets)
                    elif c.target:
                        targets.append(c.target)

        if not targets:
            return text, "missing_target"

        if has_it:
            if len(targets) == 1:
                return re.sub(r"\bit\b", targets[0], text, flags=re.IGNORECASE), None
            else:
                return text, "ambiguous"

        if has_first:
            if len(targets) >= 1:
                t = re.sub(r"\bthe first (one|tab|result)\b", targets[0], text, flags=re.IGNORECASE)
                t = re.sub(r"\bfirst (one|tab|result)\b", targets[0], t, flags=re.IGNORECASE)
                return t, None
            else:
                return text, "missing_target"

        if has_second:
            if len(targets) >= 2:
                t = re.sub(r"\bthe second (one|tab|result)\b", targets[1], text, flags=re.IGNORECASE)
                t = re.sub(r"\bsecond (one|tab|result)\b", targets[1], t, flags=re.IGNORECASE)
                return t, None
            else:
                return text, "missing_target"

        return text, None
