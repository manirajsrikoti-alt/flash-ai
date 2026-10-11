"""FLASH continuous microphone prototype — transcription only."""

import os
import queue
import threading
import time
from typing import Optional

import mlx_whisper
import numpy as np
import sounddevice as sd

SAMPLE_RATE = 16000
MICROPHONE_DEVICE = 0
BLOCK_SECONDS = 0.1
# Configurable silence timeout (default 0.5s = 500 ms, within 450-600ms range)
SILENCE_SECONDS = float(os.getenv("FLASH_SILENCE_SECONDS", "0.5"))
MIN_SPEECH_SECONDS = 0.35
MAX_UTTERANCE_SECONDS = 12
QUEUE_MAX_SIZE = 50  # Bounded queue: ~5 seconds of 100ms blocks

audio_queue = queue.Queue(maxsize=QUEUE_MAX_SIZE)

_whisper_lock = threading.Lock()
_whisper_warmed_up = False


def warmup_whisper() -> bool:
    """Pre-warm MLX Whisper model in background to avoid first-call latency."""
    global _whisper_warmed_up
    with _whisper_lock:
        if _whisper_warmed_up:
            return True
        try:
            dummy_audio = np.zeros(int(SAMPLE_RATE * 0.5), dtype=np.float32)
            mlx_whisper.transcribe(
                dummy_audio,
                path_or_hf_repo="mlx-community/whisper-small-mlx",
                language="en",
                condition_on_previous_text=False,
            )
            _whisper_warmed_up = True
            return True
        except Exception:
            return False


class Utterance(str):
    """String with attached timing instrumentation metadata."""
    timings: dict

    def __new__(cls, text: str, timings: Optional[dict] = None):
        obj = super().__new__(cls, text)
        obj.timings = timings or {}
        return obj


def drain_queue(q: queue.Queue, max_keep: int = 1) -> int:
    """Drain stale audio blocks accumulated while consumer was blocked."""
    dropped = 0
    while q.qsize() > max_keep:
        try:
            q.get_nowait()
            dropped += 1
        except queue.Empty:
            break
    return dropped


def listen_for_speech(
    silence_seconds: Optional[float] = None,
    return_dict: bool = False,
    device: Optional[int] = None,
):
    """Yield transcribed strings/utterances from the microphone continuously."""
    eff_silence = silence_seconds if silence_seconds is not None else SILENCE_SECONDS
    speech = []
    speaking = False
    silence_time = 0.0
    speech_time = 0.0
    noise_floor = 0.003
    last_status = time.monotonic()
    vad_start_time = 0.0

    local_queue = queue.Queue(maxsize=QUEUE_MAX_SIZE)

    def local_callback(indata, frames, time_info, status):
        if status:
            print(f"Audio status: {status}")
        try:
            local_queue.put_nowait(indata[:, 0].copy())
        except queue.Full:
            # Explicit overflow behavior: drop block, do not block audio thread
            pass

    with sd.InputStream(
        samplerate=SAMPLE_RATE,
        blocksize=int(SAMPLE_RATE * BLOCK_SECONDS),
        channels=1,
        dtype="float32",
        device=device,
        callback=local_callback,
    ):
        print("👂 FLASH is listening...")
        while True:
            try:
                block = local_queue.get(timeout=0.2)
            except queue.Empty:
                continue

            rms = float(np.sqrt(np.mean(block * block) + 1e-12))

            if not speaking:
                noise_floor = 0.98 * noise_floor + 0.02 * min(rms, 0.03)
                threshold = max(0.012, noise_floor * 3.0)

                if rms >= threshold:
                    speaking = True
                    speech = [block]
                    speech_time = BLOCK_SECONDS
                    silence_time = 0.0
                    vad_start_time = time.monotonic()
                    print("🎙️ Speech detected...")
            else:
                speech.append(block)
                speech_time += BLOCK_SECONDS

                if rms < max(0.008, noise_floor * 2.0):
                    silence_time += BLOCK_SECONDS
                else:
                    silence_time = 0.0

                if (
                    silence_time >= eff_silence
                    or speech_time >= MAX_UTTERANCE_SECONDS
                ):
                    speaking = False
                    audio = np.concatenate(speech).astype(np.float32)
                    speech = []
                    speech_duration = speech_time
                    detected_silence = silence_time

                    if speech_duration >= MIN_SPEECH_SECONDS:
                        print("🧠 Transcribing...")
                        t_transcribe_start = time.perf_counter()
                        try:
                            with _whisper_lock:
                                result = mlx_whisper.transcribe(
                                    audio,
                                    path_or_hf_repo="mlx-community/whisper-small-mlx",
                                    language="en",
                                    condition_on_previous_text=False,
                                )
                            t_transcribe_ms = (time.perf_counter() - t_transcribe_start) * 1000.0
                            transcript = result.get("text", "").strip()

                            if transcript:
                                timings = {
                                    "vad_silence_s": round(detected_silence, 3),
                                    "speech_duration_s": round(speech_duration, 3),
                                    "transcription_ms": round(t_transcribe_ms, 1),
                                }
                                if return_dict:
                                    yield {
                                        "type": "final",
                                        "text": transcript,
                                        "timings": timings,
                                    }
                                else:
                                    yield Utterance(transcript, timings)
                            else:
                                print("FLASH: No clear speech detected.")
                        except Exception as exc:
                            print(f"Transcription error: {exc}")

                    # Reset tracking state
                    speech_time = 0.0
                    silence_time = 0.0

                    # Drain stale audio accumulated during downstream execution/transcription
                    drain_queue(local_queue, max_keep=1)

            now = time.monotonic()
            if now - last_status >= 15:
                print("👂 FLASH is still listening...")
                last_status = now


def main():
    print("\n⚡ FLASH CONTINUOUS LISTENING TEST")
    print("Speak naturally. No Enter key is needed.")
    print("This stage transcribes speech but DOES NOT execute commands.")
    print("Press Ctrl+C to stop.\n")

    try:
        for transcript in listen_for_speech():
            timings = getattr(transcript, "timings", {})
            print(f"FLASH heard: {transcript} (timings: {timings})\n")
    except KeyboardInterrupt:
        print("\nFLASH continuous-listening test stopped.")


if __name__ == "__main__":
    main()
