"""Text processing utilities for tokenization, hashing, and keyword extraction."""

import hashlib
import re
from collections import Counter
from typing import List, Optional

STOPWORDS = {
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and", "any", "are",
    "as", "at", "be", "because", "been", "before", "being", "below", "between", "both", "but",
    "by", "can", "did", "do", "does", "doing", "down", "during", "each", "few", "for", "from",
    "further", "had", "has", "have", "having", "he", "her", "here", "hers", "herself", "him",
    "himself", "his", "how", "i", "if", "in", "into", "is", "it", "its", "itself", "just",
    "me", "more", "most", "my", "myself", "no", "nor", "not", "now", "of", "off", "on",
    "once", "only", "or", "other", "our", "ours", "ourselves", "out", "over", "own", "same",
    "she", "should", "so", "some", "such", "than", "that", "the", "their", "theirs", "them",
    "themselves", "then", "there", "these", "they", "this", "those", "through", "to", "too",
    "under", "until", "up", "very", "was", "we", "were", "what", "when", "where", "which",
    "while", "who", "whom", "why", "with", "would", "you", "your", "yours", "yourself",
    "yourselves",
}


def tokenize(text: str) -> List[str]:
    """Tokenize text into lowercase words, removing stopwords."""
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    tokens = [t for t in text.split() if len(t) >= 3 and t not in STOPWORDS]
    return tokens


def simhash_from_tokens(tokens: List[str]) -> Optional[int]:
    """Compute 64-bit SimHash from token list."""
    if not tokens:
        return None
    vector = [0] * 64
    for token in tokens:
        digest = hashlib.md5(token.encode("utf-8")).digest()
        h = int.from_bytes(digest[:8], "big")
        for i in range(64):
            if (h >> i) & 1:
                vector[i] += 1
            else:
                vector[i] -= 1
    value = 0
    for i, score in enumerate(vector):
        if score > 0:
            value |= 1 << i
    return value


def hamming_distance(a: int, b: int) -> int:
    """Compute Hamming distance between two integers."""
    return (a ^ b).bit_count()


def extract_keywords(text: str, max_keywords: int) -> List[str]:
    """Extract top keywords from text using term frequency."""
    tokens = tokenize(text)
    counts = Counter(tokens)
    return [w for w, _ in counts.most_common(max_keywords)]


def jaccard(a: List[str], b: List[str]) -> float:
    """Compute Jaccard similarity between two lists."""
    set_a, set_b = set(a), set(b)
    if not set_a or not set_b:
        return 0.0
    return len(set_a & set_b) / len(set_a | set_b)


def fallback_summary(text: str, max_sentences: int = 3) -> str:
    """Extract first N sentences as a fallback summary."""
    if not text:
        return ""
    sentences = re.split(r"(?<=[.!?])\s+", text)
    sentences = [s.strip() for s in sentences if s.strip()]
    return " ".join(sentences[:max_sentences])
