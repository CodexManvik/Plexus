import difflib
import math
from typing import Iterable


def text_precision(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a, b).ratio()


def cosine_similarity(a: Iterable[float], b: Iterable[float]) -> float:
    a_list = list(a)
    b_list = list(b)
    if not a_list or not b_list:
        return 0.0
    dot = sum(x * y for x, y in zip(a_list, b_list))
    norm_a = math.sqrt(sum(x * x for x in a_list))
    norm_b = math.sqrt(sum(y * y for y in b_list))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def combined_score(text_score: float, semantic_score: float, text_weight: float = 0.6) -> float:
    return (text_score * text_weight) + (semantic_score * (1.0 - text_weight))
