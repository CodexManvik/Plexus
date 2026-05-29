import re
from typing import Any, Dict, List, Optional, Tuple
from app.config import settings
from app.services.agents.grounding_agent import GroundingAgent
from app.services.logger import clm_logger


class CriticAgent:
    """
    CriticAgent — Bounded reasoner responsible for LLM output verification.
    Validates parameter values, formats, and ensures strict citation grounding.
    """

    def __init__(self):
        self.grounding_agent = GroundingAgent()

    async def validate_extraction(
        self,
        parameter_name: str,
        value: Optional[str],
        citation: Optional[str],
        pre_fetched_chunks: List[Dict[str, Any]],
        full_text: str,
        parameter_logic: str,
        retry_count: int,
    ) -> Tuple[bool, Optional[str]]:
        """
        Validates extraction output.
        Returns (is_valid, feedback_message).
        """
        param_name_clean = parameter_name.strip()
        max_retries = settings.extraction_max_critic_retries

        clm_logger.info(
            f"[CriticAgent] Validating '{param_name_clean}' | Value: {value!r} | "
            f"Citation: {citation!r} | Attempt: {retry_count + 1}/{max_retries}"
        )

        # Null extraction is a valid terminal state (parameter not found).
        if not citation and not value:
            return True, None

        # If we have a value but no citation, it's an orphan value (invalid, unless it's general metadata)
        if value and not citation:
            # Check if this parameter is general and doesn't require a specific text span
            is_general = any(
                kw in param_name_clean.lower()
                for kw in ["organization", "business_unit", "contract_type", "agreement_type"]
            )
            if not is_general:
                return False, (
                    f"VALIDATION FAILURE: Value '{value}' was provided without a supporting citation. "
                    "You must extract the exact quoted text from the document supporting this value."
                )

        # Validate citation presence in retrieved chunks or full text
        citation_verified = False
        if citation:
            # 1. Programmatic fast matching in chunks
            for chunk in pre_fetched_chunks:
                chunk_text = chunk.get("chunk_text") or ""
                # Whitespace normalized or exact check
                if self._citation_in_text(citation, chunk_text):
                    citation_verified = True
                    break

            # 2. Programmatic fast matching in full text
            if not citation_verified:
                if self._citation_in_text(citation, full_text):
                    citation_verified = True

            # 3. GroundingAgent paraphrased evidence check (hybrid LLM step!)
            if not citation_verified:
                clm_logger.info(
                    f"[CriticAgent] Programmatic citation check failed for '{param_name_clean}'. "
                    "Invoking semantic paraphrased evidence check..."
                )
                # Combine relevant chunks to form a validation corpus
                corpus = "\n\n".join(chunk.get("chunk_text") or "" for chunk in pre_fetched_chunks[:3])
                if not corpus:
                    corpus = full_text[:10000]

                if await self.grounding_agent.resolve_paraphrased_evidence(citation, corpus):
                    citation_verified = True
                    clm_logger.info(f"[CriticAgent] Semantic check PASSED for '{param_name_clean}'.")

        if citation and not citation_verified:
            return False, (
                f"VALIDATION FAILURE (attempt {retry_count + 1}/{max_retries}): "
                f"The citation string was not found in the source document. "
                f"You returned: {citation!r}. "
                "Ensure you copy the exact text from the provided excerpts — do not paraphrase."
            )

        # Value plausibility check for financial and date fields
        if value and citation_verified:
            param_logic_lower = parameter_logic.lower()
            param_name_lower = param_name_clean.lower()

            is_financial_field = any(
                kw in param_logic_lower or kw in param_name_lower
                for kw in ["payment", "amount", "rate", "price", "fee", "cost",
                           "charge", "invoice", "consideration", "salary", "compensation"]
            )
            if is_financial_field:
                # Must contain at least one numeric character (tolerating currency symbols/commas)
                if not re.search(r"[\d,]+\.?\d*", value):
                    return False, (
                        f"VALIDATION FAILURE (attempt {retry_count + 1}/{max_retries}): "
                        f"'{parameter_name}' is a financial field but the value '{value}' contains "
                        "no numeric amount. Extract the specific monetary value or rate."
                    )

        return True, None

    def _normalize_ws(self, text: str) -> str:
        return re.sub(r"\s+", " ", text).strip().lower()

    def _citation_in_text(self, citation: str, text: str) -> bool:
        if citation in text:
            return True
        norm_cite = self._normalize_ws(citation)
        norm_text = self._normalize_ws(text)
        return bool(norm_cite and norm_cite in norm_text)
