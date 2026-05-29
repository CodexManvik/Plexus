import re
import difflib
from typing import Tuple
from app.services.llm import local_llm
from app.services.logger import clm_logger


class GroundingAgent:
    """
    GroundingAgent — Bounded reasoner responsible for citation grounding,
    OCR repair, and fuzzy text span alignment.
    """

    async def resolve_paraphrased_evidence(self, citation: str, corpus: str) -> bool:
        """
        Determines whether the citation is semantically present in the corpus
        (allowing for paraphrased or re-ordered legal text).
        """
        if not citation or not corpus:
            return False

        # Fast path: exact or normalized exact check
        citation_clean = re.sub(r"\s+", " ", citation).strip().lower()
        corpus_clean = re.sub(r"\s+", " ", corpus).strip().lower()
        if citation_clean in corpus_clean:
            return True

        # Fallback path: GGUF local model (or Cohere)
        system_prompt = (
            "You are a legal document evidence validator. Your task is to verify if a given "
            "citation matches the meaning of text in a provided document corpus, allowing for minor "
            "paraphrasing, legal jargon formatting, or OCR spelling issues.\n"
            "Return ONLY 'TRUE' if the citation matches the meaning of a clause in the corpus, "
            "and 'FALSE' if it does not. Do not explain your reasoning."
        )
        user_prompt = f"Citation: {citation}\n\nCorpus excerpt: {corpus}"

        clm_logger.info("[GroundingAgent] Resolving paraphrased evidence via local inference tier...")
        res = await local_llm.get_completion(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_tokens=10,
            temperature=0.0,
        )
        val = res.strip().upper()
        clm_logger.info(f"[GroundingAgent] Local inference returned: {val}")
        return "TRUE" in val

    async def repair_ocr_noise(self, text: str) -> str:
        """
        Cleans up OCR spelling and layout spacing errors using the local inference tier.
        """
        if not text or not text.strip():
            return ""

        system_prompt = (
            "You are an OCR text repair service. Clean up spelling, spacing, and hyphenation "
            "issues caused by digital document scanning. Do not change legal terms or paraphrase the "
            "sentences. Return only the corrected text."
        )
        user_prompt = f"Text to repair:\n{text}"

        clm_logger.info("[GroundingAgent] Repairing OCR noise via local inference tier...")
        repaired = await local_llm.get_completion(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_tokens=400,
            temperature=0.0,
        )
        return repaired.strip() if repaired else text

    async def align_fuzzy_span(self, text: str, citation: str) -> Tuple[int, int]:
        """
        Resolves character start and end offsets of a citation within a document text block,
        utilizing Python's SequenceMatcher for high-fidelity alignment when exact matching fails.
        """
        if not text or not citation:
            return 0, 0

        # Exact match
        idx = text.find(citation)
        if idx != -1:
            return idx, idx + len(citation)

        # Case-insensitive
        idx = text.lower().find(citation.lower())
        if idx != -1:
            return idx, idx + len(citation)

        # Whitespace-tolerant exact search
        cite_clean = re.sub(r"\s+", " ", citation).strip().lower()
        text_clean = re.sub(r"\s+", " ", text).lower()
        idx = text_clean.find(cite_clean)
        if idx != -1:
            # We must map back the offset to the raw text.
            # SequenceMatcher will do this perfectly.
            pass

        # SequenceMatcher alignment (fuzzy substring locator)
        clm_logger.info(f"[GroundingAgent] Performing fuzzy span alignment for citation: '{citation[:40]}...'")
        s = difflib.SequenceMatcher(None, text.lower(), citation.lower())
        match = s.find_longest_match(0, len(text), 0, len(citation))
        if match.size > 15:
            # We matched a significant portion of the citation!
            start = match.a
            end = match.a + match.size
            clm_logger.info(f"[GroundingAgent] Fuzzy alignment success: offsets ({start}, {end})")
            return start, end

        # Fallback to first line or sentence match
        first_line = [line for line in citation.splitlines() if len(line.strip()) > 15]
        if first_line:
            first = first_line[0].strip()
            idx = text.lower().find(first.lower())
            if idx != -1:
                return idx, idx + len(first)

        return 0, 0
