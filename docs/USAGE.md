# FLASH AI — Command & Usage Guide

This document details every verified command, expected behavior, required permissions, confirmation requirements, and failure modes in FLASH AI.

---

## 1. Command Reference Table

| Category | Command / Intent | Example Voice Input | Confirmation | Permissions Needed | Behavior & Limitation Notes |
| :--- | :--- | :--- | :---: | :--- | :--- |
| **System Apps** | `open_calculator` | *"Open Calculator"* | None | None | Launches `/System/Applications/Calculator.app`. |
| **System Apps** | `open_chrome` | *"Launch Google Chrome"* | None | None | Launches Google Chrome browser. |
| **System Apps** | `open_youtube` | *"Go to YouTube"* | None | None | Opens `https://www.youtube.com` in Google Chrome. |
| **System Apps** | `record_video` | *"Record a video"* | None | None | Launches QuickTime Player. |
| **System Apps** | `view_photos` | *"Show my photos"* | None | None | Launches macOS Photos app. |
| **Apple Notes** | `create_note` | *"Create a note titled Meeting with body Discuss roadmap"* | None | Automation > Notes | Creates a new note in Apple Notes via JXA. Verifies creation; rejects empty titles. |
| **Apple Notes** | `create_note` | *"Take a note: buy groceries for dinner"* | None | Automation > Notes | Auto-extracts title and body. Safe note bodies with words like "buy" are permitted. |
| **Photo Booth** | `open_camera` | *"Open camera"*, *"Open Photo Booth"* | None | None | Launches Photo Booth without triggering shutter. |
| **Photo Booth** | `capture_photo` | *"Take a photo"*, *"Capture photo"* | None | Accessibility | Activates Photo Booth, triggers spacebar shutter (`key code 49`), and checks library for new image. Reports error `-1719` if Accessibility permission is missing. |
| **WhatsApp** | `open_whatsapp` | *"Open WhatsApp"* | None | None | Launches WhatsApp without drafting or sending. |
| **WhatsApp** | `prepare_whatsapp_message` | *"Send a WhatsApp message to Alice saying I will be late"* | **Required** | None (uses URL scheme) | Extracts recipient & message. Displays preview and asks for confirmation. Upon `"yes"`, opens `whatsapp://send` draft. Explains manual send limitation. |
| **Web Search** | `web_search` | *"Search for quantum computing"* | None | None | Validates query (1–500 chars) and opens Google Search in default browser. |
| **Websites** | `open_website` | *"Open Wikipedia"*, *"Visit GitHub"* | None | None | Opens domain in default browser. Only allowlisted domains and safe HTTP(S) URLs accepted. |
| **Conversation** | `tell_joke` | *"Tell me a joke"* | None | None | Deterministic offline joke response. |
| **Task Flow** | `confirm` / `cancel` | *"Yes"*, *"Proceed"*, *"No"*, *"Cancel"* | N/A | None | Confirms or aborts an active task awaiting confirmation. |
| **Task Flow** | `followup_continue` | *"Continue"*, *"Do the next step"* | None | None | Advances to the next pending step of an active multi-step plan. |
| **Task Flow** | `followup_retry` | *"Retry"* | None | None | Retries the last failed step without re-running succeeded steps. |
| **Task Flow** | `reset` | *"Reset"* | None | None | Clears active conversation turns and task context. |
| **Session** | `quit` | *"Quit"*, *"Exit"* | None | None | Gracefully shuts down CLI and closes floating pill UI. |

---

## 2. Detailed Integration Guides

### A. Apple Notes
- **Supported Syntaxes:**
  - *"Create a note titled `<title>` with body `<body>`"*
  - *"Create a note titled `<title>` with text `<body>`"*
  - *"Take a note: `<body>`"*
  - *"Make a note titled `<title>`"*
- **Validation & Safety Rules:**
  - Title must be between 1 and 200 characters.
  - Body must not exceed 10,000 characters.
  - Null bytes (`\x00`) are rejected.
  - Data is passed strictly through environment variables (`FLASH_NOTE_TITLE`, `FLASH_NOTE_BODY`) to static JXA code, preventing script injection.
- **Verification:**
  - The JXA script activates Notes, pushes the note object to the default account, and returns `{"success": true, "title": "..."}`.
  - If Apple Events permission is missing, returns: `Automation failed (check Privacy & Security > Automation > Notes)`.

### B. Photo Booth
- **Distinguishing Actions:**
  - *"Open camera"* or *"Open Photo Booth"* only launches the application (`open -a "Photo Booth"`).
  - *"Take a photo"*, *"Take a picture"*, or *"Capture photo"* initiates the shutter sequence.
- **Execution Mechanism:**
  - Activates Photo Booth application.
  - Dispatches `key code 49` (spacebar) via System Events.
- **Truthful Status Reporting:**
  - If macOS Accessibility permission is not granted, returns:
    `Photo Booth opened, but taking a photo requires macOS Accessibility permissions (-1719) (System Settings > Privacy & Security > Accessibility). Please grant access or press the shutter manually.`
  - If executed, inspects `~/Pictures/Photo Booth Library/Pictures`. If a newly saved picture is found, returns:
    `Photo captured in Photo Booth: <filename.jpg>.`
  - If the shutter fired but the file cannot be independently confirmed, reports:
    `Photo Booth shutter triggered, but photo file could not be independently verified in the library.`

### C. WhatsApp Messaging Flow
- **Safety Rule:** Silent or automated background sending is strictly forbidden.
- **Workflow:**
  1. **User Request:** *"Send a WhatsApp message to Alice saying I'm running 5 minutes late."*
  2. **Field Extraction:** Recipient is resolved to `"Alice"`, message body to `"I'm running 5 minutes late"`.
  3. **Clarification (if incomplete):**
     - If user says *"Send a WhatsApp message to Alice"*, FLASH asks: *"What message would you like to send to Alice on WhatsApp?"*
     - If user says *"Send a WhatsApp message saying Hello"*, FLASH asks: *"Who would you like to message on WhatsApp?"*
  4. **Confirmation Gate:** Once recipient and message are resolved, FLASH enters the `awaiting_confirmation` phase:
     > *"I have prepared a WhatsApp message for Alice: 'I'm running 5 minutes late'. Would you like to proceed? Say 'yes' to confirm or 'no' to cancel."*
  5. **User Decision:**
     - User says *"No"* / *"Cancel"*: FLASH cancels the task: *"Action cancelled."*
     - User says *"Yes"* / *"Proceed"*: FLASH opens the pre-populated message via URL scheme (`whatsapp://send?text=...`) and returns:
       > *"Opened WhatsApp with draft for Alice: 'I'm running 5 minutes late'. Note: macOS WhatsApp does not support automatic background sending; please review and click Send in WhatsApp."*

### D. Safety Gate & Blocked Operations
FLASH AI enforces a conservative safety gate. The following requests are unconditionally blocked from execution:
- **File & System Deletion:** *"delete all my files"*, *"rm -rf /"*, *"format disk"*.
- **Privilege Escalation:** *"sudo shutdown"*, *"run root command"*.
- **Financial Transactions:** *"pay $500"*, *"buy a laptop on Amazon"*, *"transfer funds"*.
- **Credential Access:** *"show my password"*, *"read my tokens"*.
- **Unverified Messaging:** *"send an email to Alice"*, *"send a message to my boss"* (only verified WhatsApp drafting with confirmation is supported).

Blocked commands output:
> `FLASH> This request is blocked by the current safety policy.`
