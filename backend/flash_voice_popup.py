"""FLASH AI Voice Assistant — Dynamic Island / Capsule Floating Popup UI.

Compact borderless floating pill overlay matching macOS voice assistant aesthetics.
All Tkinter operations run strictly on the UI main thread via a thread-safe Queue.
"""

import queue
import time
import math
from typing import Optional, Callable

try:
    import tkinter as tk
except ImportError:
    tk = None


class FlashVoicePopup:
    """Thread-safe controller and view for the compact floating voice pill."""

    WIDTH = 420
    HEIGHT = 42
    Y_OFFSET = 32  # Just beneath the macOS menu bar

    # Theme colors
    BG_COLOR = "#1C1C1E"       # Dark system capsule
    ACCENT_COLOR = "#0A84FF"   # Blue
    LISTEN_COLOR = "#30D158"   # Green
    PROCESS_COLOR = "#BF5AF2"  # Purple
    SPEAK_COLOR = "#FF9F0A"    # Amber
    PLAN_COLOR = "#5E5CE6"     # Indigo
    EXEC_COLOR = "#0A84FF"     # Blue
    FAIL_COLOR = "#FF453A"     # Red
    TEXT_COLOR = "#F2F2F7"     # Off-white
    MUTED_TEXT = "#8E8E93"     # Secondary label
    CLOSE_BG = "#2C2C2E"       # Dismiss button pill
    CLOSE_FG = "#FF453A"       # Close accent (subtle red/coral)

    def __init__(self, headless: bool = False, on_dismiss: Optional[Callable[[], None]] = None):
        self.headless = headless or (tk is None)
        self.on_dismiss = on_dismiss
        self._command_queue: queue.Queue = queue.Queue()
        self._dismissed = False
        self._running = False

        # Current UI model state
        self.current_state = "idle"       # "idle", "listening", "processing", "speaking"
        self.current_transcript = ""
        self.current_response = ""
        self._anim_frame = 0

        # Tkinter handles
        self.root: Optional[tk.Tk] = None
        self.canvas: Optional[tk.Canvas] = None
        self._text_item: Optional[int] = None
        self._bars: list[int] = []

        if not self.headless:
            try:
                self._init_window()
            except Exception as e:
                # Graceful fallback to headless if display server is unavailable
                self.headless = True
                self.root = None

    def _init_window(self):
        self.root = tk.Tk()
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.configure(bg=self.BG_COLOR)

        screen_w = self.root.winfo_screenwidth()
        x = max(0, (screen_w - self.WIDTH) // 2)
        y = self.Y_OFFSET
        self.root.geometry(f"{self.WIDTH}x{self.HEIGHT}+{x}+{y}")

        self.canvas = tk.Canvas(
            self.root,
            width=self.WIDTH,
            height=self.HEIGHT,
            bg=self.BG_COLOR,
            highlightthickness=0,
        )
        self.canvas.pack(fill="both", expand=True)

        self._draw_capsule()
        self._init_waveform()
        self._init_text()
        self._init_dismiss_button()

    def _draw_capsule(self):
        w, h = self.WIDTH, self.HEIGHT
        r = h // 2
        # Pill outer background
        self.canvas.create_arc((0, 0, 2 * r, h), start=90, extent=180, fill=self.BG_COLOR, outline="")
        self.canvas.create_arc((w - 2 * r, 0, w, h), start=270, extent=180, fill=self.BG_COLOR, outline="")
        self.canvas.create_rectangle((r, 0, w - r, h), fill=self.BG_COLOR, outline="")

        # Subtle border ring for contrast against light wallpapers
        self.canvas.create_arc((1, 1, 2 * r - 1, h - 1), start=90, extent=180, outline="#3A3A3C", width=1)
        self.canvas.create_arc((w - 2 * r + 1, 1, w - 1, h - 1), start=270, extent=180, outline="#3A3A3C", width=1)
        self.canvas.create_line((r, 1, w - r, 1), fill="#3A3A3C", width=1)
        self.canvas.create_line((r, h - 1, w - r, h - 1), fill="#3A3A3C", width=1)

    def _init_waveform(self):
        """Draw 5 vertical waveform bars on the left."""
        self._bars = []
        bar_x = 22
        for i in range(5):
            line = self.canvas.create_line(
                bar_x + i * 5, 21 - 3,
                bar_x + i * 5, 21 + 3,
                fill=self.LISTEN_COLOR,
                width=2,
                capstyle="round"
            )
            self._bars.append(line)

    def _init_text(self):
        self._text_item = self.canvas.create_text(
            58, 21,
            anchor="w",
            text="Listening...",
            fill=self.TEXT_COLOR,
            font=("Helvetica", 12, "normal")
        )

    def _init_dismiss_button(self):
        w, h = self.WIDTH, self.HEIGHT
        cx, cy = w - 24, h // 2
        r = 10

        # Clickable circular hit area
        self.canvas.create_oval(
            cx - r, cy - r, cx + r, cy + r,
            fill=self.CLOSE_BG, outline="",
            tags="dismiss_btn"
        )
        # Stop square icon inside
        sq = 4
        self.canvas.create_rectangle(
            cx - sq, cy - sq, cx + sq, cy + sq,
            fill=self.CLOSE_FG, outline="",
            tags="dismiss_btn"
        )

        self.canvas.tag_bind("dismiss_btn", "<Button-1>", lambda _: self._handle_ui_dismiss())

    def _handle_ui_dismiss(self):
        self._dismissed = True
        if self.on_dismiss:
            self.on_dismiss()
        self.close()

    # --- Thread-Safe Public API (Called from Worker Threads) ---

    def set_state(self, state: str):
        """Update popup state: 'idle', 'listening', 'processing', 'speaking'."""
        self.current_state = state
        self._command_queue.put(("state", state))

    def set_transcript(self, text: str):
        """Update live speech transcript."""
        self.current_transcript = text
        self._command_queue.put(("transcript", text))

    def set_response(self, text: str):
        """Update FLASH AI response text."""
        self.current_response = text
        self._command_queue.put(("response", text))

    def is_dismissed(self) -> bool:
        return self._dismissed

    def request_close(self):
        """Tell the UI event loop to shut down cleanly."""
        self._command_queue.put(("close", None))

    # --- UI Thread Processing ---

    def _process_queue(self):
        while not self._command_queue.empty():
            try:
                cmd, val = self._command_queue.get_nowait()
            except queue.Empty:
                break

            if cmd == "state":
                self.current_state = val
                self._update_display_text()
            elif cmd == "transcript":
                self.current_transcript = val
                self._update_display_text()
            elif cmd == "response":
                self.current_response = val
                self._update_display_text()
            elif cmd == "close":
                self.close()
                return

    def _update_display_text(self):
        if self.headless or not self.canvas:
            return

        display_text = ""
        text_color = self.TEXT_COLOR

        if self.current_state == "listening":
            display_text = self.current_transcript if self.current_transcript else "Listening..."
            text_color = self.TEXT_COLOR if self.current_transcript else self.MUTED_TEXT
        elif self.current_state == "transcribing":
            display_text = "Transcribing speech..."
            text_color = self.PROCESS_COLOR
        elif self.current_state in ("processing", "understanding"):
            display_text = f"Thinking: {self.current_transcript}" if self.current_transcript else "Thinking..."
            text_color = self.PROCESS_COLOR
        elif self.current_state == "planning":
            display_text = f"Planning: {self.current_transcript}" if self.current_transcript else "Planning task..."
            text_color = self.PLAN_COLOR
        elif self.current_state == "executing":
            display_text = f"Executing: {self.current_response or self.current_transcript}"
            text_color = self.EXEC_COLOR
        elif self.current_state in ("awaiting_confirmation", "confirming"):
            display_text = f"Confirm: {self.current_response}" if self.current_response else "Awaiting confirmation..."
            text_color = self.SPEAK_COLOR
        elif self.current_state == "awaiting_clarification":
            display_text = self.current_response if self.current_response else "Clarification needed..."
            text_color = self.SPEAK_COLOR
        elif self.current_state == "completed":
            display_text = self.current_response if self.current_response else "Done"
            text_color = self.LISTEN_COLOR
        elif self.current_state == "failed":
            display_text = self.current_response if self.current_response else "Failed"
            text_color = self.FAIL_COLOR
        elif self.current_state == "speaking":
            display_text = self.current_response if self.current_response else "Responding..."
            text_color = self.SPEAK_COLOR
        else:
            display_text = "FLASH ⚡ Ready"
            text_color = self.MUTED_TEXT

        # Truncate text with ellipsis if too long to fit comfortably (max ~38 chars)
        max_chars = 40
        if len(display_text) > max_chars:
            display_text = display_text[:max_chars - 3] + "..."

        self.canvas.itemconfig(self._text_item, text=display_text, fill=text_color)

    def _animate(self):
        if self.headless or not self.canvas or not self.root:
            return

        self._anim_frame += 1
        color = self.LISTEN_COLOR

        if self.current_state in ("processing", "transcribing", "understanding"):
            color = self.PROCESS_COLOR
        elif self.current_state == "planning":
            color = self.PLAN_COLOR
        elif self.current_state == "executing":
            color = self.EXEC_COLOR
        elif self.current_state in ("speaking", "awaiting_confirmation", "confirming", "awaiting_clarification"):
            color = self.SPEAK_COLOR
        elif self.current_state == "completed":
            color = self.LISTEN_COLOR
        elif self.current_state == "failed":
            color = self.FAIL_COLOR
        elif self.current_state == "idle":
            color = "#636366"

        cy = 21
        for i, line in enumerate(self._bars):
            if self.current_state == "listening":
                # Subtle rhythmic pulse
                offset = math.sin(self._anim_frame * 0.25 + i * 0.8)
                h = 4 + int(abs(offset) * 8)
            elif self.current_state in ("processing", "transcribing", "understanding", "planning"):
                # Traveling wave
                offset = math.sin(self._anim_frame * 0.4 + i * 1.2)
                h = 3 + int((offset + 1.0) * 5)
            elif self.current_state == "executing":
                # Faster traveling wave
                offset = math.sin(self._anim_frame * 0.6 + i * 1.5)
                h = 4 + int((offset + 1.0) * 6)
            elif self.current_state in ("speaking", "awaiting_confirmation", "awaiting_clarification"):
                # Dynamic speech bouncing
                offset = math.sin(self._anim_frame * 0.35 + i * 1.5)
                h = 5 + int(abs(offset) * 11)
            elif self.current_state == "completed":
                h = 4
            elif self.current_state == "failed":
                h = 2
            else:
                h = 2

            self.canvas.coords(line, 22 + i * 5, cy - h, 22 + i * 5, cy + h)
            self.canvas.itemconfig(line, fill=color)

    def run_mainloop(self, poll_interval_ms: int = 40):
        """Main Tkinter loop. Blocks on the UI thread until close() is called."""
        if self.headless:
            # Headless mode loop: just poll queue until closed
            self._running = True
            while self._running:
                self._process_queue()
                time.sleep(poll_interval_ms / 1000.0)
            return

        self._running = True

        def _tick():
            if not self._running or not self.root:
                return
            self._process_queue()
            self._animate()
            if self._running and self.root:
                self.root.after(poll_interval_ms, _tick)

        self.root.after(poll_interval_ms, _tick)
        try:
            self.root.mainloop()
        except KeyboardInterrupt:
            self.close()

    def close(self):
        """Destroy window and terminate mainloop."""
        self._running = False
        if self.root:
            try:
                self.root.destroy()
            except Exception:
                pass
            self.root = None
