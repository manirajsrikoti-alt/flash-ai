
"""FLASH Voice Assistant — microphone input, text output only."""

from pathlib import Path

import mlx_whisper
import sounddevice as sd
from scipy.io.wavfile import write

from flash_aws_brain import FlashAWSBrain
from flash_nlp import analyze_transcript
from flash_router import route
from flash_executor import execute
from flash_laya_classifier import classify


SAMPLE_RATE = 16000
RECORD_SECONDS = 8
MICROPHONE_DEVICE = 0
AUDIO_PATH = Path(__file__).resolve().parent / "flash_voice_input.wav"


def listen_and_transcribe() -> str:
    print(f"\nFLASH 🎙️ Listening for {RECORD_SECONDS} seconds...")
    print("Speak now.")

    audio = sd.rec(
        int(RECORD_SECONDS * SAMPLE_RATE),
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype="int16",
        device=MICROPHONE_DEVICE,
    )
    sd.wait()
    write(str(AUDIO_PATH), SAMPLE_RATE, audio)

    print("FLASH 🧠 Transcribing...")
    result = mlx_whisper.transcribe(
        str(AUDIO_PATH),
        path_or_hf_repo="mlx-community/whisper-small-mlx",
        language="en",
    )
    return result.get("text", "").strip()


def main() -> None:
    print("\n⚡ FLASH VOICE ASSISTANT")
    print("FAST INTELLIGENCE. INSTANT ACTION.")
    print("Speak for 8 seconds per turn.")
    print("Type 'q' and press Enter to quit.")
    print("Answers appear as text. FLASH will not speak aloud.\n")

    brain = FlashAWSBrain()

    while True:
        try:
            choice = input("Press Enter to speak, or q to quit: ").strip().lower()
            if choice == "q":
                break

            transcript = listen_and_transcribe()
            if not transcript:
                print("FLASH> I couldn't detect speech. Please try again.")
                continue

            analysis = analyze_transcript(transcript)
            cleaned_text = analysis.cleaned_text

            print(f"\nYou said: {transcript}")
            print(f"FLASH understood: {cleaned_text}")

            if not cleaned_text:
                print("FLASH> Please try speaking again.")
                continue

            decision = route(cleaned_text, classifier=classify)

            if decision.intent != "unknown":
                result = execute(decision.intent, decision.target)
                print(f"FLASH> {result.message}\n")
                continue

            answer = brain.ask(cleaned_text)
            print(f"\nFLASH> {answer}\n")

        except KeyboardInterrupt:
            print("\nFLASH stopped.")
            break
        except Exception as exc:
            print(f"\nFLASH> An error occurred: {exc}")
            print("Check the microphone, transcription setup, and logs.")

    print("FLASH stopped.")


if __name__ == "__main__":
    main()
