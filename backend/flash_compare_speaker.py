import numpy as np
import sounddevice as sd
import torch
import torch.nn.functional as F
from speechbrain.inference.speaker import EncoderClassifier

SAMPLE_RATE = 16000
RECORD_SECONDS = 5
MICROPHONE_DEVICE = 0

print("Loading speaker model...")
classifier = EncoderClassifier.from_hparams(
    source="speechbrain/spkrec-ecapa-voxceleb",
    savedir="../.speaker-models/ecapa",
    run_opts={"device": "cpu"},
)
print("Model loaded.")

volunteer_samples = []
prompts = [
    "Hello FLASH, this is my first voice sample.",
    "I am testing my voice in a classroom environment.",
    "FLASH should recognize my voice and ignore other speakers.",
]

print("\nAsk a consenting volunteer to read each sentence.")
print("Use the same MacBook microphone and approximately the same distance.")

for i, prompt in enumerate(prompts, start=1):
    input(f"\nVolunteer sample {i}/3. Press Enter, then read:\n{prompt}\n")
    print("Recording for 5 seconds...")
    audio = sd.rec(
        int(RECORD_SECONDS * SAMPLE_RATE),
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype="float32",
        device=MICROPHONE_DEVICE,
    )
    sd.wait()

    rms = float(np.sqrt(np.mean(audio ** 2)))
    print(f"Audio level (RMS): {rms:.4f}")
    if rms < 0.005:
        print("WARNING: Recording is very quiet.")

    waveform = torch.from_numpy(audio[:, 0].copy()).unsqueeze(0)
    with torch.no_grad():
        embedding = classifier.encode_batch(waveform)

    volunteer_samples.append(
        F.normalize(embedding.reshape(1, -1), dim=1)
    )
    print(f"Volunteer sample {i} processed.")

print("\nVolunteer-to-volunteer similarities:")
for i in range(len(volunteer_samples)):
    for j in range(i + 1, len(volunteer_samples)):
        score = F.cosine_similarity(
            volunteer_samples[i], volunteer_samples[j]
        ).item()
        print(f"Volunteer {i + 1} vs {j + 1}: {score:.4f}")

print("\nComparison recording test completed.")
print("Audio files were not saved; embeddings remained in memory.")
print("No commands were executed.")
