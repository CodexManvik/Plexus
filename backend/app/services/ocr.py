from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List


SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
WORD_RE = re.compile(r"[A-Za-z0-9_]+")


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _tokenize(text: str) -> List[str]:
    return [token.lower() for token in WORD_RE.findall(text) if len(token) > 1]


def _split_sentences(text: str) -> List[str]:
    normalized = _normalize(text)
    if not normalized:
        return []
    return [segment.strip() for segment in SENTENCE_SPLIT_RE.split(normalized) if segment.strip()]


@dataclass
class MatchResult:
    text: str
    start: int
    end: int
    score: float


def _find_best_sentence(document_text: str, terms: Iterable[str]) -> MatchResult:
    normalized = _normalize(document_text)
    sentences = _split_sentences(normalized)
    if not sentences:
        return MatchResult(text="", start=0, end=0, score=0.0)

    lowered_terms = [term.lower() for term in terms if term]
    best = MatchResult(text="", start=0, end=0, score=0.0)
    cursor = 0

    for sentence in sentences:
        lowered_sentence = sentence.lower()
        hits = sum(1 for term in lowered_terms if term in lowered_sentence)
        score = hits / max(1, len(lowered_terms))
        if hits > 0 and score >= best.score:
            start = normalized.find(sentence, cursor)
            if start == -1:
                start = normalized.find(sentence)
            end = start + len(sentence)
            best = MatchResult(text=sentence, start=max(0, start), end=max(0, end), score=score)
        cursor += len(sentence) + 1

    return best


def _build_spatial_json(start: int, end: int) -> Dict[str, Any]:
    return {
        "page": 1,
        "box": [start, 0, end, 0],
    }


class DynamicExtractionEngine:
    async def run_extraction_for_rules(
        self,
        document_text: str,
        rules: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        normalized_text = _normalize(document_text)

        for rule in rules:
            param_head = rule.get("parameter_head", "").strip()
            param_name = rule.get("parameter_name", "").strip() or param_head
            param_logic = (rule.get("parameter_logic") or "").strip()

            search_terms = list(dict.fromkeys(_tokenize(f"{param_head} {param_name} {param_logic}")))
            match = _find_best_sentence(normalized_text, search_terms)

            extracted = match.text or ""
            score = round(match.score, 3) if extracted else 0.0

            results.append(
                {
                    "header_name": param_head or "General",
                    "param_name": param_name or "Extracted Parameter",
                    "original_extract": extracted,
                    "user_override": None,
                    "match_score": score,
                    "citation_text": extracted,
                    "citation_start": match.start if extracted else None,
                    "citation_end": match.end if extracted else None,
                    "spatial_json": _build_spatial_json(match.start, match.end) if extracted else None,
                    "vector_embed": None,
                    "source_query": param_logic or param_name,
                }
            )

        return results


extraction_engine = DynamicExtractionEngine()
