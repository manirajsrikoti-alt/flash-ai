import json
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote_plus, urlsplit


ALLOWED_SITES = {"youtube": "https://www.youtube.com"}

ACTIONS = {
    "open_calculator": ["open", "-a", "Calculator"],
    "open_chrome": ["open", "-a", "Google Chrome"],
    "open_youtube": ["open", "-a", "Google Chrome", ALLOWED_SITES["youtube"]],
    "open_whatsapp": ["open", "-a", "WhatsApp"],
    "open_notes": ["open", "-a", "Notes"],
    "open_camera": ["open", "-a", "Photo Booth"],
    "open_photo_booth": ["open", "-a", "Photo Booth"],
    "record_video": ["open", "-a", "QuickTime Player"],
    "view_photos": ["open", "-a", "Photos"],
}

JOKE = "Why do programmers prefer dark mode? Because light attracts bugs."
TIMEOUT_SECONDS = 10


@dataclass(frozen=True)
class ExecResult:
    ok: bool
    message: str


def _validated_url(target: str) -> str | None:
    """Accept HTTP(S) URLs or ordinary domain names; reject unsafe schemes."""
    if not isinstance(target, str):
        return None

    target = target.strip()
    if not target or any(ord(ch) < 32 for ch in target):
        return None

    # Treat a bare domain such as wikipedia.org as HTTPS.
    if "://" not in target:
        if target.startswith("//"):
            return None
        target = "https://" + target

    try:
        parsed = urlsplit(target)
        hostname = parsed.hostname
        if parsed.scheme.lower() not in {"http", "https"}:
            return None
        if not hostname or "." not in hostname:
            return None
        if parsed.username is not None or parsed.password is not None:
            return None
        if any(ch.isspace() for ch in hostname):
            return None
        # Force port parsing so malformed ports are rejected.
        _ = parsed.port
    except ValueError:
        return None

    return target


def _open_url(url: str) -> ExecResult:
    try:
        proc = subprocess.run(
            ["open", url],
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
            check=False,
        )
    except FileNotFoundError:
        return ExecResult(False, "The macOS 'open' command was not found.")
    except subprocess.TimeoutExpired:
        return ExecResult(False, "Opening the website timed out.")
    except OSError as exc:
        return ExecResult(False, f"Could not open website: {type(exc).__name__}")

    if proc.returncode != 0:
        return ExecResult(False, "macOS could not open that website.")
    return ExecResult(True, "Website opened in the macOS default browser.")


def _capture_photo() -> ExecResult:
    """Attempt to trigger the Photo Booth shutter and verify capture."""
    try:
        open_proc = subprocess.run(
            ["open", "-a", "Photo Booth"],
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
            check=False,
        )
        if open_proc.returncode != 0:
            return ExecResult(False, "Could not open Photo Booth; check whether it is installed.")
    except FileNotFoundError:
        return ExecResult(False, "The macOS 'open' command was not found.")
    except subprocess.TimeoutExpired:
        return ExecResult(False, "Launching Photo Booth timed out.")
    except OSError as exc:
        return ExecResult(False, f"Failed to launch Photo Booth: {type(exc).__name__}")

    # Inspect Photo Booth library before shutter trigger
    photo_library = Path.home() / "Pictures" / "Photo Booth Library" / "Pictures"
    existing_photos = set()
    if photo_library.is_dir():
        try:
            existing_photos = {p.name for p in photo_library.iterdir() if p.is_file()}
        except OSError:
            pass

    # Photo Booth has no native AppleScript capture command; trigger shutter via System Events spacebar
    script = (
        'tell application "Photo Booth" to activate\n'
        'tell application "System Events"\n'
        '    tell process "Photo Booth"\n'
        '        key code 49\n'
        '    end tell\n'
        'end tell'
    )
    try:
        proc = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
            check=False,
        )
    except FileNotFoundError:
        return ExecResult(False, "The macOS 'osascript' command was not found.")
    except subprocess.TimeoutExpired:
        return ExecResult(False, "Photo Booth shutter trigger timed out.")
    except OSError as exc:
        return ExecResult(False, f"Photo Booth shutter automation failed: {type(exc).__name__}")

    if proc.returncode != 0:
        err = (proc.stderr or "").lower()
        if "-1719" in err or "assistive access" in err or "not allowed" in err:
            return ExecResult(
                False,
                "Photo Booth opened, but taking a photo requires macOS Accessibility permissions (-1719) "
                "(System Settings > Privacy & Security > Accessibility). Please grant access or press the shutter manually."
            )
        return ExecResult(
            False,
            f"Photo Booth shutter automation failed: {proc.stderr.strip() or 'Unknown error'}. "
            "Photo Booth is open; please press the shutter manually."
        )

    # Verification: check if a new photo was written to the library
    new_photos = []
    if photo_library.is_dir():
        time.sleep(0.5)
        try:
            current_photos = {p.name for p in photo_library.iterdir() if p.is_file()}
            new_photos = sorted(list(current_photos - existing_photos))
        except OSError:
            pass

    if new_photos:
        return ExecResult(True, f"Photo captured in Photo Booth: {new_photos[-1]}.")

    return ExecResult(
        True,
        "Photo Booth shutter triggered, but photo file could not be independently verified in the library."
    )


def prepare_whatsapp_message(recipient: str, message: str) -> ExecResult:
    """Prepare a WhatsApp message draft and open WhatsApp safely."""
    recipient = (recipient or "").strip()
    message = (message or "").strip()
    if not recipient:
        return ExecResult(False, "Recipient is required to prepare a WhatsApp message.")
    if not message:
        return ExecResult(False, "Message content is required to prepare a WhatsApp message.")
    if any(ord(ch) < 32 for ch in message if ch not in ("\n", "\t")):
        return ExecResult(False, "Message contains invalid control characters.")
    if len(message) > 4000:
        return ExecResult(False, "Message exceeds maximum length of 4000 characters.")

    encoded_msg = quote_plus(message)
    clean_phone = re.sub(r"[\s()\-]", "", recipient)
    clean_digits = clean_phone.lstrip("+")
    if re.fullmatch(r"\d{7,15}", clean_digits):
        phone_param = f"phone={clean_digits}&"
    else:
        phone_param = ""

    url = f"whatsapp://send?{phone_param}text={encoded_msg}"
    try:
        proc = subprocess.run(
            ["open", url],
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
            check=False,
        )
    except FileNotFoundError:
        return ExecResult(False, "The macOS 'open' command was not found.")
    except subprocess.TimeoutExpired:
        return ExecResult(False, "Opening WhatsApp timed out.")
    except OSError as exc:
        return ExecResult(False, f"Could not launch WhatsApp: {type(exc).__name__}")

    if proc.returncode != 0:
        try:
            subprocess.run(["open", "-a", "WhatsApp"], timeout=TIMEOUT_SECONDS, check=False)
        except Exception:
            pass
        return ExecResult(
            False,
            f"Could not open WhatsApp draft for {recipient}. Ensure WhatsApp is installed."
        )

    return ExecResult(
        True,
        f"Opened WhatsApp with draft for {recipient}: \"{message}\". "
        "Note: macOS WhatsApp does not support automatic sending; please review and click Send in WhatsApp."
    )


def execute(intent: str, target: str | None = None) -> ExecResult:
    if intent == "tell_joke":
        return ExecResult(True, JOKE)

    if intent == "open_website":
        url = _validated_url(target or "")
        if url is None:
            return ExecResult(
                False,
                "Invalid website URL. Use a valid domain or an HTTP(S) URL.",
            )
        return _open_url(url)

    if intent == "web_search":
        query = (target or "").strip()
        if not query or len(query) > 500:
            return ExecResult(False, "Please provide a search query of 1–500 characters.")
        if any(ord(ch) < 32 for ch in query):
            return ExecResult(False, "Search query contains invalid control characters.")
        url = "https://www.google.com/search?q=" + quote_plus(query)
        return _open_url(url)

    if intent == "capture_photo":
        return _capture_photo()

    if intent in {"prepare_whatsapp_message", "send_whatsapp_message"}:
        recipient = ""
        msg_text = ""
        if isinstance(target, dict):
            recipient = target.get("recipient", "")
            msg_text = target.get("message", "")
        elif isinstance(target, str):
            try:
                data = json.loads(target)
                if isinstance(data, dict):
                    recipient = data.get("recipient", "")
                    msg_text = data.get("message", "")
            except Exception:
                pass
            if not recipient and "::" in target:
                recipient, _, msg_text = target.partition("::")
            elif not recipient:
                recipient = target
        return prepare_whatsapp_message(recipient, msg_text)

    if intent == "create_note":
        title = ""
        body = ""
        if isinstance(target, dict):
            title = str(target.get("title", ""))
            body = str(target.get("body", ""))
        elif isinstance(target, str):
            target_str = target.strip()
            if target_str.startswith("{") and target_str.endswith("}"):
                try:
                    data = json.loads(target_str)
                    if isinstance(data, dict):
                        title = str(data.get("title", ""))
                        body = str(data.get("body", ""))
                except Exception:
                    pass
            if not title and "::" in target_str:
                title, _, body = target_str.partition("::")
            elif not title and "\n" in target_str:
                title, _, body = target_str.partition("\n")
            elif not title:
                title = target_str
                body = target_str

        from flash_plan_executor import _create_note
        res = _create_note(title.strip(), body.strip() if body else title.strip())
        return ExecResult(res.ok, res.message)

    argv = ACTIONS.get(intent)
    if argv is None:
        return ExecResult(False, "Unsupported action; nothing was executed.")

    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
            check=False,
        )
    except FileNotFoundError:
        return ExecResult(False, "The requested app or macOS 'open' command was not found.")
    except subprocess.TimeoutExpired:
        return ExecResult(False, "The action timed out.")
    except OSError as exc:
        return ExecResult(False, f"Could not run the action: {type(exc).__name__}")

    if proc.returncode != 0:
        return ExecResult(False, "The action failed; check whether the app is installed.")

    return ExecResult(True, f"Done: {intent}")
