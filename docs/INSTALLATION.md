# FLASH AI — Installation Guide

This guide provides copy-paste instructions to install, configure, and run FLASH AI on macOS.

---

## 1. System Requirements

- **Operating System:** macOS 13 (Ventura), macOS 14 (Sonoma), or macOS 15 (Sequoia).
- **Hardware:** Apple Silicon (M1, M2, M3, M4) is strongly recommended for hardware-accelerated local transcription via Apple MLX. Intel Macs are supported for CLI and text routing.
- **Python Version:** Python 3.11, 3.12, or 3.13.
- **Audio:** Built-in microphone or external USB/Bluetooth microphone.

---

## 2. Quick-Start Setup

### Step 1: Clone the Repository
```bash
git clone https://github.com/manirajsrikoti-alt/flash-ai.git
cd flash-ai
```

### Step 2: Create a Virtual Environment
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### Step 3: Install Dependencies
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

> **Note on Apple Silicon Acceleration:** `mlx-whisper` compiles Metal shaders on first execution. Ensure your active Python environment is native `arm64` (not running under Rosetta). Verify by running:
> ```bash
> python3 -c "import platform; print(platform.machine())"  # Should output: arm64
> ```

---

## 3. Configuration & Credentials

Local commands (Calculator, Notes, Photo Booth, Chrome, YouTube, local search, and intent classification) function **completely offline without any external API keys**.

To enable general conversational AI and multi-step task planning via Amazon Bedrock:

1. Copy the template:
   ```bash
   cp .env.example .env
   ```
2. Edit `.env` with your preferred editor:
   ```env
   AWS_ACCESS_KEY_ID=your_aws_access_key
   AWS_SECRET_ACCESS_KEY=your_aws_secret_key
   FLASH_AWS_REGION=us-east-1
   FLASH_BEDROCK_MODEL=us.amazon.nova-2-lite-v1:0
   FLASH_SILENCE_SECONDS=0.5
   ```
3. Ensure your AWS IAM identity has `bedrock:InvokeModel` and `bedrock:Converse` permissions enabled for Amazon Nova Lite.

---

## 4. Required macOS System Permissions

FLASH AI interacts with macOS desktop features through standard system APIs. Grant the following permissions in **System Settings > Privacy & Security**:

| Permission Category | Required By | Instructions |
| :--- | :--- | :--- |
| **Microphone** | Live speech capture (`sounddevice`) | When running `--voice` for the first time, macOS will display a prompt asking for microphone access. Click **Allow**. If missed, toggle your terminal app on in `Privacy & Security > Microphone`. |
| **Automation** | Apple Notes JXA automation | Required to create Notes. When creating your first note, macOS prompts: *"Terminal wants access to control Notes"*. Click **OK**. Verify under `Privacy & Security > Automation`. |
| **Accessibility** | Photo Booth shutter automation | Required for System Events to trigger the spacebar shutter (`key code 49`). Add your terminal emulator (e.g., Terminal, iTerm2, or VS Code) under `Privacy & Security > Accessibility`. |

---

## 5. Running FLASH AI

### Text Mode (Interactive Terminal)
Ideal for testing without microphone hardware:
```bash
python backend/flash_cli.py
```
Type commands naturally:
```text
you> open calculator
FLASH> Done: open_calculator
you> create a note titled Project Alpha with body Review code today
FLASH> Created Notes note: 'Project Alpha'.
you> quit
```

### Continuous Voice Mode (Live Assistant)
Starts continuous voice listening and displays the macOS floating capsule pill UI:
```bash
python backend/flash_cli.py --voice
```
Speak commands naturally into your microphone without pressing Enter or holding push-to-talk buttons.

### Component Diagnostic Tests
Verify individual subsystems before full execution:

- **Microphone & Speech Transcription:**
  ```bash
  python backend/flash_voice_continuous.py
  ```
- **Floating Capsule UI:**
  ```bash
  python backend/flash_voice_popup.py
  ```
- **AWS Bedrock Brain (Optional):**
  ```bash
  python backend/flash_aws_brain.py
  ```

---

## 6. Running the Test Suite

Run the full automated test suite (all tests mock OS calls and run completely offline without side effects):
```bash
pytest -v
```
Expected output:
```text
============================= 153 passed in 13.69s =============================
```
