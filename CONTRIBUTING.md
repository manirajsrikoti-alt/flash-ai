# Contributing to FLASH AI

Thank you for your interest in contributing to FLASH AI! This project aims to deliver fast intelligence and instant action for macOS through local-first intent classification, verified app automation, and safety-gated execution.

---

## Development Workflow

### 1. Prerequisites
- macOS running on Apple Silicon (M1/M2/M3/M4 recommended for MLX Whisper acceleration) or Intel Mac.
- Python 3.11+ (Python 3.13 recommended).
- macOS permissions granted for Terminal / Python:
  - **Microphone**: For live voice input.
  - **Automation**: For Apple Notes JXA control.
  - **Accessibility**: For Photo Booth shutter keyboard events.

### 2. Environment Setup
1. Clone the repository:
   ```bash
   git clone https://github.com/manirajsrikoti-alt/flash-ai.git
   cd flash-ai
   ```
2. Create and activate a virtual environment:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Copy the environment template:
   ```bash
   cp .env.example .env
   ```

---

## Coding Guidelines

1. **Safety First**:
   - Never bypass the safety gates (`BLOCKED_PATTERN` in `flash_cli.py` and `DANGEROUS` in `flash_router.py`).
   - Consequential operations (such as messaging, payments, or file deletions) must require explicit user confirmation.
   - External shell commands must be strictly allowlisted with argument lists (`argv`), never raw `shell=True` string execution.

2. **Truthful Reporting**:
   - If an automated task cannot be verified independently, report the limitation honestly instead of claiming false success.
   - Do not claim partial streaming transcription if the underlying speech recognition stack only yields completed utterances.

3. **Deterministic Fast Path**:
   - Local actions (Calculator, Notes, Chrome, Photo Booth, WhatsApp drafting) must execute deterministically without unnecessary cloud API calls.
   - Use the Laya intent classifier for fast (<10 ms) local semantic matching.

4. **Testing Integrity**:
   - Automated tests **must mock macOS automation and subprocess calls**. Never trigger real shutters, create real notes, or send live messages during test suite execution.
   - Ensure all tests pass before opening a pull request:
     ```bash
     pytest -v
     ```

---

## Pull Request Process

1. Fork the repository and create your feature branch from `main`:
   ```bash
   git checkout -b feature/my-new-feature
   ```
2. Implement your changes following existing code conventions.
3. Add focused unit tests covering the new functionality.
4. Run the full test suite and ensure all tests pass:
   ```bash
   pytest
   ```
5. Commit your changes with clear, descriptive commit messages:
   ```bash
   git commit -m "Add support for Calendar event scheduling"
   ```
6. Push to your fork and submit a Pull Request against `main`.

---

## Reporting Issues

If you find a bug or have a feature request:
- Search existing issues to avoid duplicates.
- Provide your macOS version, Python version, exact command or speech input, and relevant log outputs.
- For security vulnerabilities, please refer to [SECURITY.md](SECURITY.md).
