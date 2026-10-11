"""Layer A: deterministic parser + Layer B: model output validation."""
import re
from dataclasses import dataclass
from typing import Callable, Optional, Tuple

SUPPORTED_INTENTS = {
    "open_calculator", "open_chrome", "open_youtube",
    "open_whatsapp", "open_notes", "create_note", "open_camera", "open_photo_booth",
    "capture_photo", "record_video", "view_photos", "tell_joke"
}
MODEL_MIN_CONFIDENCE = 0.85

DANGEROUS = re.compile(
    r"\b(delete|remove|erase|format|wipe|rm|sudo|send|message|email|text|"
    r"pay|buy|purchase|transfer|password|token|credential|shutdown|install)\b"
)

_VERB = r"(?:open|launch|start|run)"
_THE = r"(?:the |a |an )?"
_RULES = [
    ("open_calculator", "Calculator", re.compile(
        rf"^{_VERB} {_THE}(?:apple )?calculator(?: app| application)?$"
    )),
    ("open_chrome", "Google Chrome", re.compile(
        rf"^{_VERB} {_THE}(?:google )?chrome(?: browser| app)?$"
    )),
    ("open_whatsapp", "WhatsApp", re.compile(
        rf"^{_VERB} {_THE}whatsapp(?: app)?$"
    )),
    ("open_notes", "Notes", re.compile(
        rf"^{_VERB} {_THE}(?:apple )?notes(?: app)?$"
    )),
    ("open_youtube", "youtube.com", re.compile(
        rf"^(?:{_VERB}|go to|take me to) (?:youtube|you tube)"
        rf"(?: (?:in|on|with) (?:google )?chrome)?$"
    )),
    ("open_camera", "Photo Booth", re.compile(
        rf"^{_VERB} {_THE}camera(?: app| application)?$"
    )),
    ("open_photo_booth", "Photo Booth", re.compile(
        rf"^{_VERB} {_THE}photo booth(?: app| application)?$"
    )),
    ("capture_photo", "Photo Booth", re.compile(
        rf"^(?:take|capture|snap|click) {_THE}(?:photo|picture)(?: with photo booth| with camera)?$"
    )),
    ("tell_joke", None, re.compile(
        r"^(?:tell me a joke|tell a joke|tell me another joke|say a joke)$"
    )),
]

SITE_ALIASES = {
    "wikipedia": "wikipedia.org",
    "google": "google.com",
    "github": "github.com",
    "reddit": "reddit.com",
    "linkedin": "linkedin.com",
    "amazon": "amazon.com",
    "instagram": "instagram.com",
    "facebook": "facebook.com",
    "x": "x.com",
    "twitter": "x.com",
    "stackoverflow": "stackoverflow.com",
    "stack overflow": "stackoverflow.com",
    "netflix": "netflix.com",
    "bbc": "bbc.com",
    "openai": "openai.com",
    "centle.in": "centle.in",
}

_SEARCH_PATTERNS = [
    re.compile(r"^(?:search (?:the web|online|google) for) (.+)$"),
    re.compile(r"^search for (.+)$"),
    re.compile(r"^search (.+)$"),
    re.compile(r"^(?:look up|google) (.+)$"),
]
_WEBSITE_PATTERNS = [
    re.compile(r"^(?:open|visit|browse to|go to|take me to) (?:the )?(.+)$"),
]
_NOTE_PATTERNS = [
    re.compile(
        r"^(?:create|make|add|take)(?: a)? note titled (.+?) with (?:body|content|text) (.+)$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(?:create|make|add)(?: a)? note titled (.+)$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(?:create|make|add)(?: a)? note (?:with (?:body|content|text)|that says) (.+)$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(?:take|create|make)(?: a)? note:\s*(.+)$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(?:take|create|make)(?: a)? note (.+)$",
        re.IGNORECASE,
    ),
]


@dataclass(frozen=True)
class Decision:
    intent: str
    source: str
    reason: str
    target: Optional[str] = None


def normalize_keep_case(text: str) -> str:
    t = (text or "").strip()
    t = re.sub(r"^(?:hey flash|flash|please|can you|could you)[,\s]+", "", t, flags=re.IGNORECASE)
    t = re.sub(r"[?!.,]+$", "", t)
    return re.sub(r"\s+", " ", t).strip()


def normalize(text: str) -> str:
    t = (text or "").lower().strip()
    t = re.sub(r"^(?:hey flash|flash|please|can you|could you)[,\s]+", "", t)
    t = re.sub(r"[?!.,]+$", "", t)
    return re.sub(r"\s+", " ", t).strip()


def parse_rules(text: str) -> Optional[Tuple[str, Optional[str]]]:
    t = normalize(text)
    for intent, target, pattern in _RULES:
        if pattern.fullmatch(t):
            return intent, target
    return None


def route(
    text: str,
    classifier: Optional[Callable[[str], Tuple[str, float]]] = None,
    min_confidence: float = MODEL_MIN_CONFIDENCE,
) -> Decision:
    t = normalize(text)
    if not t:
        return Decision("unknown", "none", "empty input")

    # Reject Markdown links before website routing.
    if "[" in (text or "") and "]" in (text or "") and "(" in (text or ""):
        return Decision("unknown", "rejected", "Markdown links are not accepted")

    # Reject shell metacharacters.
    if any(ch in t for ch in ("`", "$", "|", ";", "&", "[", "]", "<", ">")):
        return Decision("unknown", "rejected", "unsafe command syntax")

    # Preserve exact existing local commands first.
    rule_match = parse_rules(t)
    if rule_match:
        intent, target = rule_match
        return Decision(intent, "rule", "exact pattern match", target)

    # Check for note creation patterns before the generic dangerous word filter,
    # so that notes with bodies containing common words (e.g. "buy milk", "text mom")
    # are routed safely to create_note.
    import json as _json
    raw_norm = normalize_keep_case(text)
    for idx, pattern in enumerate(_NOTE_PATTERNS):
        match = pattern.fullmatch(raw_norm)
        if match:
            if idx == 0:
                title = match.group(1).strip()
                body = match.group(2).strip()
            elif idx == 1:
                title = match.group(1).strip()
                body = ""
            else:
                body = match.group(1).strip()
                title = body.split("\n")[0][:50].strip() or "Note"
            if title:
                target_json = _json.dumps({"title": title, "body": body})
                return Decision("create_note", "rule", "note creation phrase matched", target_json)

    # Keep the conservative safety gate ahead of new action routing.
    if DANGEROUS.search(t):
        return Decision(
            "unknown", "rejected",
            "consequential or dangerous request; not supported"
        )

    for pattern in _SEARCH_PATTERNS:
        match = pattern.fullmatch(t)
        if match:
            query = match.group(1).strip()
            if query:
                return Decision(
                    "web_search", "rule", "web-search phrase matched", query
                )
            return Decision("unknown", "none", "empty search query")

    for pattern in _WEBSITE_PATTERNS:
        match = pattern.fullmatch(t)
        if match:
            site = match.group(1).strip()
            if not site:
                return Decision("unknown", "none", "empty website target")

            # Defense in depth: never open Markdown-formatted links.
            if "[" in site or "]" in site or "(" in site:
                return Decision(
                    "unknown", "rejected",
                    "Markdown links are not accepted"
                )

            target = SITE_ALIASES.get(site, site)
            is_known_site = site in SITE_ALIASES

            if is_known_site:
                return Decision(
                    "open_website", "rule",
                    "recognized website target", target
                )

            # For explicit URLs, only allow those whose hostname matches
            # a known SITE_ALIASES domain (security: no arbitrary URLs).
            if target.startswith(("http://", "https://")):
                try:
                    from urllib.parse import urlsplit as _urlsplit
                    hostname = _urlsplit(target).hostname or ""
                except Exception:
                    hostname = ""
                allowed_domains = set(SITE_ALIASES.values())
                if any(
                    hostname == d or hostname.endswith("." + d)
                    for d in allowed_domains
                ):
                    return Decision(
                        "open_website", "rule",
                        "recognized website target", target
                    )
            break

    if classifier is None:
        return Decision("unknown", "none", "no rule matched and no model available")

    try:
        label, conf = classifier(t)
    except Exception as exc:
        return Decision("unknown", "none", f"classifier error: {type(exc).__name__}")

    if label not in SUPPORTED_INTENTS:
        return Decision("unknown", "model", f"model label {label!r} not allowlisted")
    if not isinstance(conf, (int, float)) or conf < min_confidence:
        return Decision("unknown", "model", f"confidence {conf} below {min_confidence}")
    return Decision(label, "model", f"model accepted at {conf:.2f}")
