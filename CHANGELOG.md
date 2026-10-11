# Changelog

All notable changes to FLASH AI are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.0.0] - 2026-10-11

### Added
- **Apple Notes Integration**: Verified note creation supporting titles and bodies via static JXA automation with environment variable data passing and execution verification.
- **Photo Booth Integration**: Dispatched shutter automation via System Events spacebar (`key code 49`), with automatic macOS Accessibility permission (`-1719`) error detection and library picture file verification.
- **WhatsApp Messaging Flow**: Recipient resolution, clarification questions for missing fields, and mandatory user confirmation (`awaiting_confirmation`) prior to drafting in WhatsApp via the `whatsapp://` URL scheme.
- **Context, Phase, and Task Manager**: Structured session manager (`TaskContext`) tracking multi-turn history, active tasks, step-by-step progress, follow-up references (`"continue"`, `"retry"`), pronoun resolution (`"it"`, `"the first one"`), and context expiration.
- **Voice Latency Optimization**: Pre-warmed MLX Whisper model (`mlx-community/whisper-small-mlx`) and Laya intent classifier in background threads to eliminate first-turn inference delay.
- **Configurable VAD**: Configurable silence timeout (default 0.5s / 500 ms) and bounded queue audio capture preventing buffer bloat.
- **Dynamic Floating Pill Popup**: Native macOS floating pill overlay with state-dependent color themes and waveform animations.
- **Multi-Step AI Planner**: Integrated AWS Bedrock task planning engine for complex multi-step instructions with dry-run safety validation.
- **Comprehensive Test Suite**: 153 offline unit and integration tests covering routing, execution, planning, safety gates, and task state progression.

### Fixed
- Fixed unhandled `create_note` routing in Layer C executor.
- Fixed `capture_photo` erroneously reporting completion when merely launching Photo Booth.
- Fixed `BLOCKED_PATTERN` over-matching valid note commands containing common words like "text" or "buy".
- Fixed variable scoping for executor dispatch in CLI confirmation loops.
