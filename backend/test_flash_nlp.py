
from flash_nlp import analyze_transcript

examples = [
    "Hey FLASH, explain machine learning in two lines.",
    "Here flies explaining machine learning in two lines.",
    "Hair flash, open calculator.",
    "Open Google Chrome.",
    "Tell me a joke.",
    "What is osmosis?",
]

for example in examples:
    result = analyze_transcript(example)
    print(f"\nOriginal: {result.original_text}")
    print(f"Cleaned: {result.cleaned_text}")
    print(f"Intent hint: {result.intent_hint}")
    print(f"Notes: {result.notes}")
