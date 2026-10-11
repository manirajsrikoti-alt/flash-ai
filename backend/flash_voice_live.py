"""FLASH live transcript prototype — transcription only."""

import queue
import threading
import time
from collections import deque

import mlx_whisper
import numpy as np
import sounddevice as sd

SAMPLE_RATE = 16000
MICROPHONE_DEVICE = 0
BLOCK_SECONDS = 0.1
PREVIEW_INTERVAL = 2.0
SILENCE_SECONDS = 1.0
MAX_UTTERANCE_SECONDS = 12.0
MIN_SPEECH_SECONDS = 0.45

audio_queue = queue.Queue(maxsize=200)
stop_event = threading.Event()


def audio_callback(indata, frames, time_info, status):
    if status:
        print(f"Audio status: {status}")

    block = indata[:, 0].copy()
    try:
        audio_queue.put_nowait(block)
    except queue.Full:
        # Never block the real-time microphone callback.
        print("Audio queue full; a block was skipped.")


def transcribe(audio):
    result = mlx_whisper.transcribe(
        np.asarray(audio, dtype=np.float32),
        path_or_hf_repo="mlx-community/whisper-small-mlx",
        language="en",
        condition_on_previous_text=False,
        temperature=0.0,
        no_speech_threshold=0.6,
    )
    return result.get("text", "").strip()


def main():
    print("\n⚡ FLASH LIVE TRANSCRIPTION — STAGE 2B")
    print("Speak naturally. No Enter key is needed.")
    print("Transcription only: commands will NOT execute.")
    print("Press Ctrl+C to stop.\n")

    pre_roll = deque(maxlen=5)
    phrase = []
    speaking = False
    speech_seconds = 0.0
    silence_seconds = 0.0
    last_preview_time = 0.0
    last_preview_text = ""
    last_rms = 0.0
    noise_floor = 0.003
    threshold = 0.012

    def process_phrase(audio, final=False):
        label = "final" if final else "preview"
        print(f"🧠 Whisper {label}...")
        try:
            text = transcribe(audio)
            if text:
                print(f"FLASH {label}: {text}")
            elif final:
                print("FLASH final: No clear speech detected.")
        except Exception as exc:
            print(f"Whisper error: {exc}")

    try:
        with sd.InputStream(
            samplerate=SAMPLE_RATE,
            blocksize=int(SAMPLE_RATE * BLOCK_SECONDS),
            channels=1,
            dtype="float32",
            device=MICROPHONE_DEVICE,
            callback=audio_callback,
        ):
            while not stop_event.is_set():
                try:
                    block = audio_queue.get(timeout=0.2)
                except queue.Empty:
                    continue

                rms = float(np.sqrt(np.mean(block * block) + 1e-12))
                now = time.monotonic()

                if not speaking:
                    noise_floor = 0.98 * noise_floor + 0.02 * min(rms, 0.03)
                    threshold = max(0.012, noise_floor * 3.0)
                    pre_roll.append(block)

                    if rms >= threshold:
                        speaking = True
                        phrase = list(pre_roll)
                        speech_seconds = len(phrase) * BLOCK_SECONDS
                        silence_seconds = 0.0
                        last_preview_time = now
                        last_preview_text = ""
                        print("🎙️ Speech detected...")
                    continue

                phrase.append(block)
                speech_seconds += BLOCK_SECONDS

                if rms < max(0.008, noise_floor * 2.0):
                    silence_seconds += BLOCK_SECONDS
                else:
                    silence_seconds = 0.0

                should_preview = (
                    now - last_preview_time >= PREVIEW_INTERVAL
                    and speech_seconds >= MIN_SPEECH_SECONDS
                    and silence_seconds < SILENCE_SECONDS
                )
                should_finalize = (
                    silence_seconds >= SILENCE_SECONDS
                    or speech_seconds >= MAX_UTTERANCE_SECONDS
                )

                if should_preview:
                    # Never launch overlapping preview jobs.
                    if not hasattr(main, "_preview_thread"):
                        main._preview_thread = None

                    current_thread = main._preview_thread
                    if current_thread is None or not current_thread.is_alive():
                        snapshot = np.concatenate(phrase).copy()
                        last_preview_time = now

                        def preview_job(audio_copy):
                            nonlocal last_preview_text
                            try:
                                text = transcribe(audio_copy)
                                if text and text != last_preview_text:
                                    last_preview_text = text
                                    print(f"\nFLASH preview: {text}")
                            except Exception as exc:
                                print(f"\nPreview error: {exc}")

                        main._preview_thread = threading.Thread(
                            target=preview_job,
                            args=(snapshot,),
                            daemon=True,
                        )
                        main._preview_thread.start()

                if should_finalize:
                    active_preview = getattr(main, "_preview_thread", None)
                    if active_preview is not None and active_preview.is_alive():
                        active_preview.join()

                    final_audio = np.concatenate(phrase).copy()
                    speaking = False
                    phrase = []
                    pre_roll.clear()
                    speech_seconds = 0.0
                    silence_seconds = 0.0
                    last_preview_text = ""

                    if len(final_audio) / SAMPLE_RATE >= MIN_SPEECH_SECONDS:
                        process_phrase(final_audio, final=True)

                    print("👂 Ready for the next phrase.\n")

    except KeyboardInterrupt:
        print("\nFLASH live transcription stopped.")
    finally:
        stop_event.set()


if __name__ == "__main__":
    main()
