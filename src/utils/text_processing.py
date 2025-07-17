"""
Utility functions for text cleaning, normalization, and chunking
"""
import re

def clean_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\n+", "\n", text)
    return text.strip()

def split_into_sentences(text: str) -> list:
    # Simple split, consider using spaCy for robustness
    return re.split(r'(?<=[.!?]) +', text)

def normalize_unicode(text: str) -> str:
    import unicodedata
    return unicodedata.normalize("NFKC", text)
