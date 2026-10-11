import threading
from laya import Router

router = Router()
_warmup_lock = threading.Lock()
_is_warmed_up = False


def warmup() -> bool:
    """Pre-warm Laya classifier model in background to avoid first-call latency."""
    global _is_warmed_up
    with _warmup_lock:
        if _is_warmed_up:
            return True
        try:
            router.predict("open calculator", QUESTIONS)
            _is_warmed_up = True
            return True
        except Exception:
            return False

QUESTIONS = {
    "intent": {
        "type": "choice",
        "instructions": (
            "Identify the user's intended task, not just the exact words or "
            "application name. Understand natural language, paraphrases, and "
            "the user's practical goal. Choose only the closest supported "
            "intent. If the request is unclear, unsupported, or consequential, "
            "choose unknown. Never send messages, delete files, make purchases, "
            "or perform other consequential actions."
        ),
        "criteria": {
            "open_calculator": (
                "The user explicitly wants to open or launch Calculator."
            ),
            "open_chrome": (
                "The user explicitly wants to open the Google Chrome browser."
            ),
            "open_youtube": (
                "The user wants YouTube opened in the browser."
            ),
            "open_whatsapp": (
                "The user explicitly wants to open WhatsApp."
            ),
            "open_notes": (
                "The user explicitly wants to open Apple Notes."
            ),
            "open_camera": (
                "The user explicitly asks to open the Camera app by name."
            ),
            "open_photo_booth": (
                "The user explicitly asks to open Photo Booth by name."
            ),
            "capture_photo": (
                "The user's goal is to take or capture a photo or still image. "
                "Examples: 'I want to capture an image', 'take a picture of me', "
                "'I need to take a photo'. Choose this even if no app is named."
            ),
            "record_video": (
                "The user's goal is to record a video or movie clip. "
                "Examples: 'record a quick video', 'I want to film something'."
            ),
            "view_photos": (
                "The user's goal is to browse or view their photo library. "
                "Examples: 'show me my photos', 'I want to look through my pictures'."
            ),
            "tell_joke": (
                "The user asks for a joke."
            ),
            "unknown": (
                "The request does not clearly match one supported intent, "
                "or asks for an unsupported or consequential action."
            ),
        },
    }
}


def classify(text: str) -> tuple[str, float]:
    """Return a supported intent label and its confidence."""
    global _is_warmed_up
    with _warmup_lock:
        result = router.predict(text, QUESTIONS)
        _is_warmed_up = True
    answer = result["answers"]["intent"]

    intent = answer.get("choice", "unknown")
    probabilities = answer.get("probabilities", {})
    confidence = probabilities.get(intent, 0.0)

    if not isinstance(intent, str):
        return "unknown", 0.0

    if not isinstance(confidence, (int, float)):
        return "unknown", 0.0

    return intent, float(confidence)
