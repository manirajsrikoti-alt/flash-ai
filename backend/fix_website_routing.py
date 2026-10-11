from pathlib import Path
import shutil
from datetime import datetime

path = Path("flash_router.py")
source = path.read_text()

start_marker = "    for pattern in _WEBSITE_PATTERNS:"
end_marker = "    if classifier is None:"

start = source.find(start_marker)
end = source.find(end_marker, start)

if start < 0 or end < 0:
    raise SystemExit("STOP: Could not locate the expected router section. No changes made.")

backup = path.with_name(
    f"flash_router.py.backup_website_{datetime.now():%Y%m%d_%H%M%S}"
)
shutil.copy2(path, backup)
print(f"Backup created: {backup.name}")

replacement = '''    for pattern in _WEBSITE_PATTERNS:
        match = pattern.fullmatch(t)
        if match:
            site = match.group(1).strip()
            if not site:
                return Decision("unknown", "none", "empty website target")

            target = SITE_ALIASES.get(site, site)
            is_explicit_url = target.startswith(("http://", "https://"))
            is_domain = "." in target and " " not in target
            is_known_site = site in SITE_ALIASES

            # Only route recognizable websites here. Let Laya interpret
            # ordinary phrases that happen to start with "open".
            if is_known_site or is_domain or is_explicit_url:
                return Decision(
                    "open_website", "rule",
                    "recognized website target", target
                )
            break

'''

updated = source[:start] + replacement + source[end:]

try:
    compile(updated, str(path), "exec")
except SyntaxError as exc:
    raise SystemExit(f"STOP: New code failed syntax check: {exc}")

path.write_text(updated)
saved = path.read_text()

assert replacement in saved
compile(saved, str(path), "exec")

print("PASS: Website-routing section saved and syntax verified.")
print("PASS: Unrecognized 'open ...' phrases can reach the classifier.")
