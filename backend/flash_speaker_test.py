import numpy as np
import sounddevice as sd
import torch
import torch.nn.functional as F
if __name__ == "__main__":
    from speechbrain.inference.speaker import EncoderClassifier
    
    SAMPLE_RATE = 16000
    RECORD_SECONDS = 5
    MICROPHONE_DEVICE = 0
    
    print("Loading FLASH speaker model...")
    classifier = EncoderClassifier.from_hparams(
        source="speechbrain/spkrec-ecapa-voxceleb",
        savedir="../.speaker-models/ecapa",
        run_opts={"device": "cpu"},
    )
    print("Model loaded.")
    
    samples = []
    prompts = [
        "Hello FLASH, this is my first voice sample.",
        "I am testing my voice in a classroom environment.",
        "FLASH should recognize my voice and ignore other speakers.",
    ]
    
    for i, prompt in enumerate(prompts, start=1):
        input(f"\nSample {i}/3. Press Enter, then read aloud:\n{prompt}\n")
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
            print("WARNING: Audio is very quiet; check the microphone.")
    
        waveform = torch.from_numpy(audio[:, 0].copy()).unsqueeze(0)
        with torch.no_grad():
            embedding = classifier.encode_batch(waveform)
    
        samples.append(F.normalize(embedding.reshape(1, -1), dim=1))
        print(f"Sample {i} processed.")
    
    print("\nCosine similarity between your samples:")
    for i in range(len(samples)):
        for j in range(i + 1, len(samples)):
            score = F.cosine_similarity(samples[i], samples[j]).item()
            print(f"Sample {i + 1} vs {j + 1}: {score:.4f}")
    
    print("\nTest completed. Audio files were not saved.")
    print("Similarity alone does not establish a safe recognition threshold.")
