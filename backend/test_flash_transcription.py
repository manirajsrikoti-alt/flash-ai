from pathlib import Path
import sounddevice as sd
import mlx_whisper

if __name__ == "__main__":
    DURATION = 8
    SAMPLE_RATE = 16000
    DEVICE = 2
    AUDIO_PATH = Path("flash_mic_test.wav")
    
    print("FLASH microphone test")
    print("Speak clearly for eight seconds...")
    audio = sd.rec(
        int(DURATION * SAMPLE_RATE),
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype="int16",
        device=DEVICE,
    )
    sd.wait()
    
    from scipy.io.wavfile import write
    write(str(AUDIO_PATH), SAMPLE_RATE, audio)
    print("Recording complete. Transcribing locally...")
    result = mlx_whisper.transcribe(
        str(AUDIO_PATH),
        path_or_hf_repo="mlx-community/whisper-small-mlx",
        language="en",
    )
    print("\nYou said:", result["text"].strip())
