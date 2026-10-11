import numpy as np
import sounddevice as sd
import torch
import torch.nn.functional as F
from speechbrain.inference.speaker import EncoderClassifier

SAMPLE_RATE = 16000
RECORD_SECONDS = 5
DEVICE = 0

PROMPTS = [
    "Hello FLASH, this is my first voice sample.",
    "I am testing my voice in a classroom environment.",
    "FLASH should recognize my voice and ignore other speakers.",
]

print("Loading FLASH speaker model...")
classifier = EncoderClassifier.from_hparams(
    source="speechbrain/spkrec-ecapa-voxceleb",
    savedir="../.speaker-models/ecapa",
    run_opts={"device": "cpu"},
)
print("Model loaded.")

embeddings = {"You": [], "Volunteer": []}

def record_embedding(speaker, index, prompt):
    input(
        f"\n{speaker} — sample {index}/3\n"
        f"Press Enter, then read aloud:\n{prompt}\n"
    )
    print(f"Recording for {RECORD_SECONDS} seconds...")
    audio = sd.rec(
        int(RECORD_SECONDS * SAMPLE_RATE),
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype="float32",
        device=DEVICE,
    )
    sd.wait()

    rms = float(np.sqrt(np.mean(audio ** 2)))
    print(f"Audio level (RMS): {rms:.4f}")

    if rms < 0.005:
        print("WARNING: Very quiet recording; results may be unreliable.")

    waveform = torch.from_numpy(audio[:, 0].copy()).unsqueeze(0)
    with torch.no_grad():
        embedding = classifier.encode_batch(waveform)

    embeddings[speaker].append(
        F.normalize(embedding.reshape(1, -1), dim=1)
    )
    print("Sample processed; audio was not saved.")

for speaker in ("You", "Volunteer"):
    print(f"\n=== Recording {speaker} ===")
    for index, prompt in enumerate(PROMPTS, start=1):
        record_embedding(speaker, index, prompt)

def similarity(a, b):
    return F.cosine_similarity(a, b).item()

print("\n=== Same-speaker similarities ===")
for speaker in embeddings:
    for i in range(3):
        for j in range(i + 1, 3):
            print(
                f"{speaker}, samples {i + 1} vs {j + 1}: "
                f"{similarity(embeddings[speaker][i], embeddings[speaker][j]):.4f}"
            )

print("\n=== Cross-speaker similarities ===")
for i in range(3):
    for j in range(3):
        print(
            f"Your sample {i + 1} vs volunteer sample {j + 1}: "
            f"{similarity(embeddings['You'][i], embeddings['Volunteer'][j]):.4f}"
        )

print("\nTest complete. Audio was not saved. No commands were executed.")
