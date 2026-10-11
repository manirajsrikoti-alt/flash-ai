# Security Policy

## Supported Versions

Security updates and critical fixes are provided for the following versions of FLASH AI:

| Version | Supported          |
| ------- | ------------------ |
| 1.0.x   | :white_check_mark: |

---

## Security Architecture & Invariants

FLASH AI is designed with strict desktop safety boundaries:

1. **Defense-in-Depth Safety Gates**:
   - Spoken commands are inspected by conservative safety filters (`BLOCKED_PATTERN` and `DANGEROUS`) that immediately block dangerous operations such as raw shell commands, file deletions, privilege escalations, financial transactions, and unapproved messaging.
   - Shell metacharacters (`` ` ``, `$`, `|`, `;`, `&`, `<`, `>`) are strictly rejected.

2. **No Raw Shell Execution**:
   - All macOS process interactions use explicit, immutable argument vectors (`subprocess.run(argv, shell=False)`), preventing command-line injection attacks.

3. **Confirmation Gates for Consequential Actions**:
   - Consequential tasks (e.g., preparing WhatsApp messages) enter an `awaiting_confirmation` phase and require explicit user confirmation (`"yes"` or `"no"`) before any action is executed.
   - Silent background message dispatch is strictly prohibited.

4. **Safe Automation Data Passing**:
   - Apple Notes creation uses JavaScript for Automation (JXA). Title and body data are passed exclusively via system environment variables (`FLASH_NOTE_TITLE`, `FLASH_NOTE_BODY`) and never interpolated directly into script strings.

5. **Allowlisted URL Schemes**:
   - Web search and browser navigation only allow validated HTTPS URLs and approved domains (`ALLOWED_SITES` / `SITE_ALIASES`).
   - Markdown-formatted links are explicitly rejected to prevent prompt injection and phishing redirects.

---

## Reporting a Vulnerability

If you discover a security vulnerability in FLASH AI, please follow responsible disclosure practices:

1. **Do not create a public GitHub issue.**
2. Send an email to the project maintainer at `manirajsrikoti@gmail.com` with:
   - A description of the vulnerability.
   - Exact steps to reproduce the issue (including voice or CLI inputs).
   - Expected impact and potential remediation.
3. We will acknowledge receipt within 48 hours and work on a resolution.
4. Once a fix has been verified and released, security credit will be provided in the changelog.
