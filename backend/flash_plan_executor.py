"""FLASH plan executor with dynamic macOS app discovery."""

import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote_plus, urlparse
import json
import os
import re

TIMEOUT_SECONDS = 10

APP_SEARCH_ROOTS = (
    Path("/Applications"),
    Path("/System/Applications"),
    Path("/System/Library/CoreServices/Applications"),
    Path.home() / "Applications",
)

WEBSITE_ALLOWLIST = {
    "youtube": "https://www.youtube.com",
    "google": "https://www.google.com",
}


@dataclass(frozen=True)
class PlanActionResult:
    ok: bool
    message: str
    extracted_targets: list[str] = field(default_factory=list)


def discover_apps() -> dict[str, Path]:
    """Discover app bundles under standard macOS application folders."""
    found = {}

    for root in APP_SEARCH_ROOTS:
        if not root.is_dir():
            continue

        try:
            candidates = root.rglob("*.app")
            for app in candidates:
                try:
                    if not app.is_dir():
                        continue
                    name = app.name[:-4].strip()
                    if name:
                        found.setdefault(name.casefold(), app)
                except OSError:
                    continue
        except OSError:
            continue

    return found


def resolve_app(target: str) -> Path | None:
    """Resolve an app by its installed bundle name or exact bundle path."""
    if not isinstance(target, str) or not target.strip():
        return None

    apps = discover_apps()
    requested = target.strip()

    # Accept a name such as "Visual Studio Code" or "Visual Studio Code.app".
    name = requested[:-4] if requested.casefold().endswith(".app") else requested
    match = apps.get(name.casefold())
    if match is not None:
        return match

    # A supplied path must resolve to a discovered installed app bundle.
    try:
        candidate = Path(requested).expanduser().resolve(strict=True)
        for app in apps.values():
            if candidate == app.resolve():
                return app
    except (OSError, RuntimeError):
        pass

    return None


def _open_app(target: str) -> PlanActionResult:
    app = resolve_app(target)
    if app is None:
        return PlanActionResult(
            False, "No matching installed app was found; nothing executed."
        )

    try:
        proc = subprocess.run(
            ["open", "-a", str(app)],
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return PlanActionResult(False, "Could not open the installed app.")

    if proc.returncode != 0:
        return PlanActionResult(False, "macOS could not open the installed app.")

    return PlanActionResult(True, f"Opened {app.name[:-4]}.")


from flash_executor import _validated_url
from flash_router import SITE_ALIASES

def normalize_website_url(target: str) -> str | None:
    """Resolve a known alias or validate a user-supplied web address against the allowlist."""
    if not isinstance(target, str) or not target.strip():
        return None

    raw = target.strip()
    alias = WEBSITE_ALLOWLIST.get(raw.casefold())
    if alias:
        return alias

    valid_url = _validated_url(raw)
    if not valid_url:
        return None

    # Reject malformed hostnames and local machine destinations.
    from urllib.parse import urlsplit
    host = (urlsplit(valid_url).hostname or "").casefold().rstrip(".")
    if host in {"localhost"} or host.endswith(".localhost"):
        return None

    # Enforce allowlist: hostname must match a domain in SITE_ALIASES
    allowed_domains = set(SITE_ALIASES.values())
    if any(host == d or host.endswith("." + d) for d in allowed_domains):
        return valid_url

    return None



SEARCH_PROVIDERS = {
    "youtube": "https://www.youtube.com/results?search_query=",
    "google": "https://www.google.com/search?q=",
    "github": "https://github.com/search?q=",
}


def normalize_search_url(provider: str, query: str) -> str | None:
    """Build a search URL only for supported providers and non-empty queries."""
    if not isinstance(provider, str) or not isinstance(query, str):
        return None
    provider = provider.strip().casefold()
    query = query.strip()
    if provider not in SEARCH_PROVIDERS or not query:
        return None
    if len(query) > 500 or any(ord(ch) < 32 for ch in query):
        return None
    return SEARCH_PROVIDERS[provider] + quote_plus(query)


def _search_web(provider: str, query: str) -> PlanActionResult:
    url = normalize_search_url(provider, query)
    if url is None:
        return PlanActionResult(False, "Invalid search provider or query; nothing executed.")
    try:
        proc = subprocess.run(
            ["open", url],
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return PlanActionResult(False, "Could not open search results.")
    if proc.returncode != 0:
        return PlanActionResult(False, "macOS could not open search results.")
    return PlanActionResult(True, f"Opened {provider.strip().title()} search results for {query!r}.")

def _open_website(target: str) -> PlanActionResult:
    site = normalize_website_url(target)
    if site is None:
        return PlanActionResult(False, "Invalid or unsafe website URL; nothing executed.")

    try:
        proc = subprocess.run(
            ["open", site],
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return PlanActionResult(False, "Could not open the website.")

    if proc.returncode != 0:
        return PlanActionResult(False, "macOS could not open the website.")

    return PlanActionResult(True, f"Opened {site} in default browser.")


def _read_chrome_tabs() -> PlanActionResult:
    script = """
    const chrome = Application("Google Chrome");
    if (!chrome.running()) {
        console.log(JSON.stringify({error: "Chrome is not running."}));
        $.exit(0);
    }
    let tabs = [];
    try {
        for (let w of chrome.windows()) {
            for (let t of w.tabs()) {
                tabs.push({title: t.title(), url: t.url()});
            }
        }
        console.log(JSON.stringify({tabs: tabs}));
    } catch (e) {
        console.log(JSON.stringify({error: e.toString()}));
    }
    """
    try:
        proc = subprocess.run(
            ["osascript", "-l", "JavaScript", "-e", script],
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS
        )
        if proc.returncode != 0:
            return PlanActionResult(False, "AppleScript execution failed (check Privacy & Security permissions).")
        
        output = proc.stdout.strip()
        if not output:
            return PlanActionResult(False, "Empty response from Chrome AppleScript.")
            
        data = json.loads(output)
        if "error" in data:
            return PlanActionResult(False, f"Chrome error: {data['error']}")
        
        tabs = data.get("tabs", [])
        if not tabs:
            return PlanActionResult(False, "No tabs are open in Chrome.")
            
        urls = [t["url"] for t in tabs]
        formatted = ", ".join(f"{t['title']} ({t['url']})" for t in tabs)
        return PlanActionResult(True, f"Read {len(tabs)} tabs: {formatted}", extracted_targets=urls)
    except json.JSONDecodeError:
        return PlanActionResult(False, "Unexpected or malformed response reading tabs.")
    except subprocess.TimeoutExpired:
        return PlanActionResult(False, "Timed out reading Chrome tabs.")
    except Exception as e:
        return PlanActionResult(False, f"Unexpected error reading tabs: {e}")


# Static JXA script for creating an Apple Notes note.
# Title and body are NEVER embedded in this string; they are passed via
# environment variables (FLASH_NOTE_TITLE / FLASH_NOTE_BODY) so that user
# text is always treated as data and can never affect the script logic.
_CREATE_NOTE_SCRIPT = """\
ObjC.import('Foundation');
var env = $.NSProcessInfo.processInfo.environment;
var title = ObjC.unwrap(env.objectForKey('FLASH_NOTE_TITLE')) || '';
var body  = ObjC.unwrap(env.objectForKey('FLASH_NOTE_BODY'))  || '';
var res;
try {
    var notes = Application('Notes');
    notes.activate();
    var account = notes.defaultAccount();
    var note = notes.Note({name: title, body: body});
    account.notes.push(note);
    res = JSON.stringify({success: true, title: title});
} catch(e) {
    res = JSON.stringify({error: e.toString()});
}
res;
"""

_NOTE_TITLE_MAX = 200
_NOTE_BODY_MAX  = 10_000


def _create_note(title: str, body: str) -> PlanActionResult:
    """Create a new Apple Notes note with the given title and body.

    Title and body are passed to the static JXA script exclusively via
    environment variables — they are never interpolated into the script string.
    """
    # --- input validation ---
    if not isinstance(title, str):
        return PlanActionResult(False, "Note title must be a string.")
    if not isinstance(body, str):
        return PlanActionResult(False, "Note body must be a string.")

    title_stripped = title.strip()
    if not title_stripped:
        return PlanActionResult(False, "Note title must not be empty.")
    if "\x00" in title:
        return PlanActionResult(False, "Note title contains an invalid null byte.")
    if len(title_stripped) > _NOTE_TITLE_MAX:
        return PlanActionResult(
            False,
            f"Note title exceeds maximum length of {_NOTE_TITLE_MAX} characters."
        )

    if "\x00" in body:
        return PlanActionResult(False, "Note body contains an invalid null byte.")
    if len(body) > _NOTE_BODY_MAX:
        return PlanActionResult(
            False,
            f"Note body exceeds maximum length of {_NOTE_BODY_MAX} characters."
        )

    # --- execute via static script + env-var data passing ---
    try:
        proc = subprocess.run(
            ["osascript", "-l", "JavaScript", "-e", _CREATE_NOTE_SCRIPT],
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
            env={**os.environ, "FLASH_NOTE_TITLE": title_stripped, "FLASH_NOTE_BODY": body},
        )
    except subprocess.TimeoutExpired:
        return PlanActionResult(False, "Timed out creating Notes note.")
    except Exception as exc:
        return PlanActionResult(False, f"Unexpected error creating Notes note: {exc}")

    if proc.returncode != 0:
        return PlanActionResult(
            False,
            "Automation failed (check Privacy & Security > Automation > Notes)."
        )

    output = proc.stdout.strip()
    if not output:
        return PlanActionResult(False, "Empty response from Notes automation.")

    try:
        data = json.loads(output)
    except json.JSONDecodeError:
        return PlanActionResult(False, "Malformed response from Notes automation.")

    if "error" in data:
        return PlanActionResult(False, f"Notes error: {data['error']}")

    if data.get("success") is not True:
        return PlanActionResult(False, "Notes automation did not confirm success.")

    return PlanActionResult(True, f"Created Notes note: {title_stripped!r}.")



def _create_text_file(filename: str, content: str) -> PlanActionResult:
    if not isinstance(filename, str) or not re.match(r"^[A-Za-z0-9_.-]+$", filename):
        return PlanActionResult(False, "Filename must be alphanumeric, containing no paths or slashes.")
    if filename in {".", ".."}:
        return PlanActionResult(False, "Filename cannot be . or ..")
        
    try:
        content_bytes = content.encode('utf-8')
    except AttributeError:
        return PlanActionResult(False, "Content must be a string.")
        
    if not content_bytes:
        return PlanActionResult(False, "Cannot create an empty file.")
        
    if len(content_bytes) > 10 * 1024 * 1024:
        return PlanActionResult(False, "File content exceeds 10MB limit.")
        
    sandbox = Path.home() / "Desktop" / "FLASH_AI_Output"
    
    sandbox.mkdir(parents=True, exist_ok=True)
    
    if sandbox.is_symlink():
        return PlanActionResult(False, "Security error: sandbox directory is a symlink.")
        
    dir_fd = None
    try:
        # Anchor file operations to the opened directory descriptor
        dir_flags = os.O_RDONLY | os.O_DIRECTORY
        if hasattr(os, "O_NOFOLLOW"):
            dir_flags |= os.O_NOFOLLOW
        dir_fd = os.open(str(sandbox), dir_flags)
    except Exception as e:
        return PlanActionResult(False, f"Security error: failed to anchor sandbox directory: {e}")
        
    try:
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
            
        fd = None
        try:
            fd = os.open(filename, flags, 0o644, dir_fd=dir_fd)
        except FileExistsError:
            return PlanActionResult(False, f"File {filename!r} already exists. Overwriting is forbidden.")
        except PermissionError:
            return PlanActionResult(False, "Permission denied when attempting to create file.")
        except Exception as e:
            return PlanActionResult(False, f"Failed to open file for writing: {e}")
            
        try:
            with os.fdopen(fd, 'wb') as f:
                f.write(content_bytes)
                f.flush()
                st = os.fstat(f.fileno())
                if st.st_size != len(content_bytes):
                    raise IOError("Written file size does not match expected content size.")
                    
            file_path = sandbox / filename
            return PlanActionResult(True, f"Created file {filename!r} in FLASH_AI_Output.", extracted_targets=[str(file_path)])
            
        except Exception as e:
            try:
                os.unlink(filename, dir_fd=dir_fd)
            except OSError:
                pass
            return PlanActionResult(False, f"Write failed or incomplete. Cleaned up partial file. Error: {e}")
    finally:
        if dir_fd is not None:
            try:
                os.close(dir_fd)
            except OSError:
                pass


def execute_step(step: dict, *, dry_run: bool = True) -> PlanActionResult:
    """Preview by default; execute only supported, validated actions."""
    if not isinstance(step, dict):
        return PlanActionResult(False, "Invalid step; nothing executed.")

    action = step.get("action")
    target = step.get("target", "")

    if not isinstance(target, str):
        return PlanActionResult(False, "Invalid target; nothing executed.")

    if action in {
        "prepare_message",
        "identify_recipients",
        "request_confirmation",
    }:
        return PlanActionResult(
            False, f"{action} is not executable by this module."
        )

    if action not in {
        "open_app", "web_search", "search_web",
        "read_chrome_tabs", "create_text_file", "create_note",
    }:
        return PlanActionResult(False, "Unsupported action; nothing executed.")

    if step.get("requires_confirmation") is not False:
        return PlanActionResult(
            False, "Step requires confirmation or has no explicit safe flag."
        )

    details = step.get("details", "")
    if not isinstance(details, str):
        return PlanActionResult(False, "Invalid details; nothing executed.")

    if action == "open_app":
        if resolve_app(target) is None:
            return PlanActionResult(
                False, "No matching installed app was found; nothing executed."
            )
    elif action == "web_search":
        if normalize_website_url(target) is None:
            return PlanActionResult(
                False, "Invalid or unsafe website URL; nothing executed."
            )
    elif action == "search_web":
        if normalize_search_url(target, details) is None:
            return PlanActionResult(
                False, "Invalid search provider or query; nothing executed."
            )

    if dry_run:
        description = (
            f"search {target!r} for {details!r}"
            if action == "search_web"
            else "read chrome tabs"
            if action == "read_chrome_tabs"
            else f"create file {target!r}"
            if action == "create_text_file"
            else f"create Notes note titled {target!r}"
            if action == "create_note"
            else f"{action} for {target!r}"
        )
        return PlanActionResult(True, f"DRY RUN: would execute {description}.")

    if action == "open_app":
        return _open_app(target)
    if action == "web_search":
        return _open_website(target)
    if action == "read_chrome_tabs":
        return _read_chrome_tabs()
    if action == "create_text_file":
        return _create_text_file(target, details)
    if action == "create_note":
        return _create_note(target, details)
    return _search_web(target, details)

