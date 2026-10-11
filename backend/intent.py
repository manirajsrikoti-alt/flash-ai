"""FLASH: safe starter intent recognizer."""

def recognize_intent(command: str) -> dict:
    text = command.strip().lower()

    if not text:
        return {"intent": "unknown", "action": None}

    if "calculator" in text and any(
        word in text for word in ("open", "launch", "start")
    ):
        return {
            "intent": "open_app",
            "action": "calculator",
            "requires_confirmation": False,
        }

    if "chrome" in text and any(
        word in text for word in ("open", "launch", "start")
    ):
        return {
            "intent": "open_app",
            "action": "chrome",
            "requires_confirmation": False,
        }

    return {
        "intent": "unknown",
        "action": None,
        "message": "I need a suitable tool or better understanding for this request.",
    }


if __name__ == "__main__":
    while True:
        command = input("\nFLASH > ")

        if command.strip().lower() in {"exit", "quit"}:
            break

        print(recognize_intent(command))
