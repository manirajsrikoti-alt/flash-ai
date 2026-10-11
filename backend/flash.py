"""FLASH: Laya-powered desktop agent."""

from time import perf_counter
from laya import Router
from executor import execute_action

router = Router()

QUESTIONS = {
    "intent": {
        "type": "choice",
        "instructions": (
            "Classify the user's intended action precisely. "
            "Choose open_calculator only for requests to open Calculator. "
            "Choose open_chrome only for requests to launch Chrome itself. "
            "Choose open_youtube when the user wants to open YouTube, "
            "including requests such as 'open YouTube in Chrome'. "
            "Choose tell_joke when the user asks for a joke. "
            "Choose unknown for every other request. "
            "Never guess when the request does not fit."
        ),
        "criteria": {
            "open_calculator": "Open or launch the Calculator app.",
            "open_chrome": "Launch the Google Chrome app itself.",
            "open_youtube": "Open the YouTube website in Google Chrome.",
            "tell_joke": "Tell a joke.",
            "unknown": "Any other, unclear, unsupported, or dangerous request.",
        },
    }
}

ACTION_MAP = {
    "open_calculator": "open_calculator",
    "open_chrome": "open_chrome",
    "open_youtube": "open_youtube",
}


def main():
    print("⚡ FLASH is ready. Type 'exit' to quit.")

    while True:
        command = input("\nYou > ").strip()

        if command.lower() in {"exit", "quit"}:
            break
        if not command:
            continue

        start = perf_counter()
        result = router.predict(command, QUESTIONS)
        elapsed = (perf_counter() - start) * 1000

        answer = result["answers"]["intent"]
        action = answer.get("choice", "unknown")
        probabilities = answer.get("probabilities", {})
        confidence = probabilities.get(action, 0.0)

        print(f"FLASH selected: {action}")
        print(f"Confidence: {confidence:.2%}")
        print(f"Decision time: {elapsed:.1f} ms")

        if action in ACTION_MAP:
            print(execute_action(ACTION_MAP[action], confidence))
        elif action == "tell_joke":
            print("Joke generation is not implemented yet.")
        else:
            print("No action taken.")


if __name__ == "__main__":
    main()
