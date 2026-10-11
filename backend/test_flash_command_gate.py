"""FLASH command-gate tests. Dry-run only; launches no apps."""

from flash_router import route

REQUIRED_MATCHES = 2
SUPPORTED = {"open_calculator", "open_chrome", "open_youtube"}


class CommandGate:
    def __init__(self):
        self.previous_intent = None
        self.match_count = 0
        self.accepted_current_phrase = False

    def process(self, transcript):
        decision = route(transcript)
        intent = decision.intent

        if intent not in SUPPORTED:
            self.previous_intent = None
            self.match_count = 0
            self.accepted_current_phrase = False
            return "REJECT", intent

        if intent != self.previous_intent:
            self.previous_intent = intent
            self.match_count = 1
            self.accepted_current_phrase = False
        else:
            self.match_count += 1

        if self.match_count >= REQUIRED_MATCHES:
            if not self.accepted_current_phrase:
                self.accepted_current_phrase = True
                return "DRY-RUN ACCEPT", intent
            return "ALREADY ACCEPTED", intent

        return f"WAIT ({self.match_count}/{REQUIRED_MATCHES})", intent

    def reset_phrase(self):
        """Call when a new utterance begins after a detected pause."""
        self.previous_intent = None
        self.match_count = 0
        self.accepted_current_phrase = False


def show(gate, transcript):
    status, intent = gate.process(transcript)
    print(f"{status}: {transcript!r} -> {intent}")


def main():
    gate = CommandGate()

    print("\n=== Test A: overlapping repeated recognition ===")
    show(gate, "Open Calculator")
    show(gate, "Open Calculator")
    show(gate, "Open Calculator")

    print("\n=== Test B: uncertain transcript resets gate ===")
    gate.reset_phrase()
    show(gate, "Open Calculator")
    show(gate, "Open Carl")
    show(gate, "Open Calculator")

    print("\n=== Test C: fresh phrase can trigger again ===")
    gate.reset_phrase()
    show(gate, "Open Calculator")
    show(gate, "Open Calculator")
    gate.reset_phrase()
    show(gate, "Open Calculator")
    show(gate, "Open Calculator")

    print("\n=== Test D: unsupported app stays rejected ===")
    gate.reset_phrase()
    show(gate, "Open WhatsApp")
    show(gate, "Open WhatsApp")


if __name__ == "__main__":
    main()
