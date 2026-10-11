from time import perf_counter
from laya import Router

if __name__ == "__main__":
    print("⚡ FLASH: Loading Laya...")
    router = Router()
    
    command = input("Enter a command: ").strip()
    
    questions = {
        "intent": {
            "type": "choice",
            "instructions": (
                "Choose the user's intended action. "
                "Do not invent an action if the request does not fit."
            ),
            "criteria": {
                "open_calculator": "The user wants to open or launch Calculator.",
                "open_chrome": "The user wants to open or launch Google Chrome.",
                "tell_joke": "The user asks the assistant to tell a joke.",
                "unknown": "The request does not match any other option.",
            },
        }
    }
    
    start = perf_counter()
    result = router.predict(command, questions)
    elapsed = (perf_counter() - start) * 1000
    
    print("\nFLASH decision:")
    print(result["answers"]["intent"])
    print(f"Inference time: {elapsed:.1f} ms")
    print("Note: this measures the prediction call, not the full voice-to-action time.")
