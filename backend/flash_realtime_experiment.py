"""FLASH real-time listening experiment — diagnostics only, no Mac actions."""

import queue
import time

import mlx_whisper
import numpy as np
import sounddevice as sd
from scipy.signal import resample_poly

SAMPLE_RATE = 48000
MICROPHONE_DEVICE = 2

WINDOW_SECONDS = 3.0
HOP_SECONDS = 1.5
BLOCK_SIZE = 4800

# Conservative starting point; adjust only after checking mic levels.
MIN_RMS = 0.005

WINDOW_SAMPLES = int(WINDOW_SECONDS * SAMPLE_RATE)
HOP_SAMPLES = int(HOP_SECONDS * SAMPLE_RATE)

audio_queue = queue.Queue(maxsize=100)


def audio_callback(indata, frames, time_info, status):
    """Capture audio quickly; never run Whisper in the callback."""
    if status:
        print(f"\nAudio status: {status}", flush=True)

    try:
        audio_queue.put_nowait(indata[:, 0].copy())
    except queue.Full:
        try:
            audio_queue.get_nowait()
            audio_queue.put_nowait(indata[:, 0].copy())
        except (queue.Empty, queue.Full):
            pass


def main():
    print("\n⚡ FLASH REAL-TIME LISTENER — EXPERIMENT")
    print("Diagnostics only: no apps will be opened.")
    print("Speak naturally. Press Ctrl+C to stop.\n")

    raw_audio = np.empty(0, dtype=np.float32)
    samples_since_transcription = 0
    last_text = ""
    started = time.perf_counter()

    try:
        with sd.InputStream(
            device=MICROPHONE_DEVICE,
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="float32",
            blocksize=BLOCK_SIZE,
            callback=audio_callback,
        ):
            while True:
                try:
                    chunk = audio_queue.get(timeout=0.25)
                except queue.Empty:
                    continue

                raw_audio = np.concatenate((raw_audio, chunk))
                samples_since_transcription += len(chunk)

                if len(raw_audio) > WINDOW_SAMPLES:
                    raw_audio = raw_audio[-WINDOW_SAMPLES:]

                if len(raw_audio) < WINDOW_SAMPLES:
                    continue

                if samples_since_transcription < HOP_SAMPLES:
                    continue

                samples_since_transcription = 0

                # Skip windows with very little audio energy.
                rms = float(np.sqrt(np.mean(np.square(raw_audio))))
                if rms < MIN_RMS:
                    last_text = ""
                    continue

                # Convert 48 kHz microphone audio to 16 kHz for Whisper.
                audio_16k = resample_poly(raw_audio, up=1, down=3)
                audio_16k = np.asarray(audio_16k, dtype=np.float32)

                started_transcription = time.perf_counter()

                result = mlx_whisper.transcribe(
                    audio_16k,
                    path_or_hf_repo="mlx-community/whisper-small-mlx",
                    language="en",
                    temperature=0.0,
                    condition_on_previous_text=False,
                    no_speech_threshold=0.6,
                    logprob_threshold=-1.0,
                    compression_ratio_threshold=2.4,
                    verbose=False,
                )

                text = result.get("text", "").strip()
                elapsed = time.perf_counter() - started_transcription
                timestamp = time.perf_counter() - started

                if text and text != last_text:
                    print(
                        f"[{timestamp:6.1f}s | inference {elapsed:.2f}s "
                        f"| RMS {rms:.4f}] {text}",
                        flush=True,
                    )

                last_text = text

    except KeyboardInterrupt:
        print("\nFLASH listening experiment stopped.")


if __name__ == "__main__":
    main()
