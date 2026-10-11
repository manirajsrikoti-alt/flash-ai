
"""FLASH NLP layer: clean speech transcripts and identify intent hints.

This module does not execute commands or override the safety router.
"""

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class NLPResult:
    original_text: str
    cleaned_text: str
    intent_hint: str
    confidence: float
    notes: str


# Only correct clear, common speech-recognition variants of the wake name.
WAKE_NAME_PATTERNS = (
    r"\bhere flies\b",
    r"\bhair flash\b",
    r"\bhey flies\b",
    r"\bhey flash\b",
)


def clean_transcript(text: str) -> str:
    """Normalize whitespace and punctuation without changing meaning."""
    cleaned = (text or "").strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = re.sub(r"\s+([,.!?])", r"\1", cleaned)
    return cleaned.strip()


def remove_wake_name(text: str) -> str:
    """Remove a recognized FLASH wake phrase only at the beginning."""
    cleaned = clean_transcript(text)

    for pattern in WAKE_NAME_PATTERNS:
        cleaned = re.sub(
            rf"^{pattern}[,.\s:!-]*",
            "",
            cleaned,
            count=1,
            flags=re.IGNORECASE,
        )
        if cleaned != text:
            break

    return cleaned.strip()


def identify_intent_hint(text: str) -> tuple[str, float, str]:
    """Return a hint for the existing router; never authorize an action."""
    normalized = clean_transcript(remove_wake_name(text)).lower()
    normalized = re.sub(r"[.!?]+$", "", normalized).strip()

    if not normalized:
        return "empty", 1.0, "No words remained after cleanup."

    if re.search(r"\b(joke|make me laugh)\b", normalized):
        return "tell_joke", 0.75, "Possible joke request."

    if re.search(r"\b(calculator)\b", normalized):
        return "open_calculator", 0.75, "Possible calculator request."

    if re.search(r"\b(chrome|browser)\b", normalized):
        return "open_chrome", 0.70, "Possible browser request."

    if re.search(r"\b(youtube|you tube)\b", normalized):
        return "open_youtube", 0.75, "Possible YouTube request."

    if re.search(
        r"\b(explain|explaining|describe|define|what is|what are|"
        r"who is|how does|how do|why does|why do|teach me|tell me about)\b",
        normalized,
    ):
        return "general_question", 0.80, "Likely conversational question."

    return "unknown", 0.0, "No clear intent hint."


def analyze_transcript(text: str) -> NLPResult:
    original = text or ""
    cleaned = clean_transcript(original)
    without_wake = remove_wake_name(cleaned)
    hint, confidence, notes = identify_intent_hint(without_wake)

    return NLPResult(
        original_text=original,
        cleaned_text=without_wake,
        intent_hint=hint,
        confidence=confidence,
        notes=notes,
    )
