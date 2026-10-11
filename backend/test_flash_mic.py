import sounddevice as sd
from scipy.io.wavfile import write

if __name__ == "__main__":
    DURATION = 5
    SAMPLE_RATE = 16000
    DEVICE = 2
    
    print("Speak a short sentence after recording starts...")
    audio = sd.rec(
        int(DURATION * SAMPLE_RATE),
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype="int16",
        device=DEVICE,
    )
    sd.wait()
    write("flash_mic_test.wav", SAMPLE_RATE, audio)
    print("Recording saved to flash_mic_test.wav")
