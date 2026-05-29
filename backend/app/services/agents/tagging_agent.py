import json
from typing import Any, Dict, Optional
from app.services.llm import cohere_llm
from app.services.logger import clm_logger


class TaggingAgent:
    """
    TaggingAgent — Dedicated bounded reasoner for upload-time metadata classification.
    Predicts contract type, business unit, risk level, jurisdiction, workflow route,
    and extraction template with confidence scores and detailed rationales.
    """

    def __init__(self):
        self.system_prompt = (
            "You are a legal contract metadata tagging agent. Your job is to analyze the text "
            "of a document and predict key metadata. You must respond ONLY with a single valid "
            "JSON object containing the following keys (each containing 'value', 'confidence' "
            "[0.0 to 1.0], and 'rationale'):\n"
            "- contract_type (e.g. 'Non-Disclosure Agreement', 'SaaS Agreement', 'Master Services Agreement', 'Employment Agreement', 'Vendor Contract')\n"
            "- business_unit (e.g. 'Legal', 'Sales', 'Procurement', 'Human Resources', 'Finance')\n"
            "- risk_level ('LOW', 'MEDIUM', 'HIGH')\n"
            "- jurisdiction (state/country name, or 'Global', 'Unknown')\n"
            "- workflow_route (e.g. 'Standard Route', 'Expedited Review', 'Executive Escalation')\n"
            "- extraction_template (e.g. 'NDA Template', 'SaaS Template', 'Vendor Template', 'General Template')\n\n"
            "Do not include any markdown formatting, backticks, or explanation outside the JSON."
        )

    async def suggest_tags(
        self,
        document_text: str,
        filename: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Runs Cohere to suggest contract metadata and rationales based on the first few pages.
        """
        # Truncate document text to the first 4000 characters to optimize token usage and focus on headers
        sample_text = document_text[:4000] if document_text else ""
        user_prompt = f"Filename: {filename or 'Unknown'}\n\nDocument Excerpt:\n{sample_text}"

        clm_logger.info("[TaggingAgent] Invoking Cohere classification...")

        response_text = await cohere_llm.get_chat_completion(
            system_prompt=self.system_prompt,
            user_prompt=user_prompt,
            response_format={"type": "json_object"},
            temperature=0.0,
            max_tokens=1000,
        )

        # Strip any formatting fences if model included them
        clean_text = response_text.strip()
        if clean_text.startswith("```"):
            lines = clean_text.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            clean_text = "\n".join(lines).strip()

        try:
            suggestions = json.loads(clean_text)
            clm_logger.info("[TaggingAgent] Suggestions successfully generated.")
            return self._ensure_schema(suggestions)
        except Exception as exc:
            clm_logger.error(
                f"[TaggingAgent] Failed to parse suggestions. Raw text was: {clean_text!r}. Error: {exc}"
            )
            return self._default_suggestions()

    def _ensure_schema(self, data: Any) -> Dict[str, Any]:
        if not isinstance(data, dict):
            return self._default_suggestions()

        expected_keys = [
            "contract_type",
            "business_unit",
            "risk_level",
            "jurisdiction",
            "workflow_route",
            "extraction_template",
        ]
        result = {}
        for key in expected_keys:
            entry = data.get(key)
            if isinstance(entry, dict) and "value" in entry:
                val = str(entry["value"]).strip()
                # Enforce allowed values for risk_level
                if key == "risk_level" and val not in ("LOW", "MEDIUM", "HIGH"):
                    val = "MEDIUM"
                result[key] = {
                    "value": val,
                    "confidence": min(max(float(entry.get("confidence") or 0.5), 0.0), 1.0),
                    "rationale": str(entry.get("rationale") or f"Predicted based on document patterns.").strip(),
                }
            else:
                # Fallback for individual key
                result[key] = {
                    "value": "Unknown" if key != "risk_level" else "MEDIUM",
                    "confidence": 0.5,
                    "rationale": "Default value due to parsing irregularity.",
                }
        return result

    def _default_suggestions(self) -> Dict[str, Any]:
        return {
            "contract_type": {"value": "General Contract", "confidence": 0.3, "rationale": "Fallback suggestion."},
            "business_unit": {"value": "Legal", "confidence": 0.3, "rationale": "Fallback suggestion."},
            "risk_level": {"value": "MEDIUM", "confidence": 0.3, "rationale": "Fallback suggestion."},
            "jurisdiction": {"value": "Unknown", "confidence": 0.3, "rationale": "Fallback suggestion."},
            "workflow_route": {"value": "Standard Route", "confidence": 0.3, "rationale": "Fallback suggestion."},
            "extraction_template": {"value": "General Template", "confidence": 0.3, "rationale": "Fallback suggestion."},
        }
