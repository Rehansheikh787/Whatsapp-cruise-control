"""
config/constants.py

Shared project constants across ingestion, parsing, and agent pipelines.
"""

ONE_WORD_ACKS = {
    # Base acknowledgements
    "ok",
    "okay",
    "k",
    "kk",
    "haan",
    "hmm",
    "thanks",
    "thank you",
    "cool",
    "nice",
    # Extracted from actual chat replies (Hinglish / texting cadence)
    "ha",
    "haa",
    "haaa",
    "han",
    "okk",
    "okh",
    "hmmm",
    "acha",
    "accha",
    "achcha",
    "thik hai",
    "ok sir",
    "done",
    "yes",
    "yep",
    "yeah",
}
