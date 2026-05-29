import json
from typing import Any, Dict, List, Tuple
from app.services.llm import cohere_llm
from app.services.logger import clm_logger


class RiskAgent:
    """
    RiskAgent — Dedicated bounded reasoner for contract risk reviews.
    Analyzes contract terms, types, and governing conditions to assign a risk score,
    risk level category, and structured risk rationale.
    """

    def __init__(self):
        self.system_prompt = (
            "You are a Senior CLM Risk Auditor. Your job is to audit legal agreements and "
            "determine their risk footprint. Analyze the provided contract type, agreement type, "
            "and extracted parameters.\n"
            "Assess the contract on key operational risks (e.g., unusual governing laws, absence of liability caps, "
            "restrictive governing conditions) and return a JSON object with exactly the following keys:\n"
            "- risk_score (a numeric score between 0.0 and 100.0, where 100.0 is extremely high risk)\n"
            "- risk_level (one of 'LOW', 'MEDIUM', 'HIGH')\n"
            "- risk_rationale (a detailed professional explanation summarizing the risk footprint)\n\n"
            "Do not include any markdown syntax or introductory text outside the JSON."
        )

    async def assess_risk(
        self,
        contract_type: str,
        agreement_type: str,
        parameters: List[Dict[str, Any]],
    ) -> Tuple[float, str, str]:
        """
        Invokes Cohere to perform risk analysis based on the extracted contract parameters.
        Returns a tuple of (risk_score, risk_level, risk_rationale).
        """
        # Format parameters for model prompt consumption
        param_list = []
        for p in parameters:
            name = p.get("param_name") or "Unnamed"
            val = p.get("user_override") or p.get("original_extract") or "Not found/Null"
            param_list.append(f"- {name}: {val}")
        params_str = "\n".join(param_list)

        user_prompt = (
            f"Contract Type: {contract_type}\n"
            f"Agreement Type: {agreement_type}\n\n"
            f"Extracted Parameter Clauses:\n{params_str}"
        )

        clm_logger.info("[RiskAgent] Auditing contract risk footprint via Cohere...")

        response_text = await cohere_llm.get_chat_completion(
            system_prompt=self.system_prompt,
            user_prompt=user_prompt,
            response_format={"type": "json_object"},
            temperature=0.0,
            max_tokens=800,
        )

        clean_text = response_text.strip()
        if clean_text.startswith("```"):
            lines = clean_text.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            clean_text = "\n".join(lines).strip()

        try:
            analysis = json.loads(clean_text)
            score = min(max(float(analysis.get("risk_score") or 30.0), 0.0), 100.0)
            level = str(analysis.get("risk_level") or "MEDIUM").strip().upper()
            if level not in ("LOW", "MEDIUM", "HIGH"):
                level = "MEDIUM"
            rationale = str(analysis.get("risk_rationale") or "Audited based on standard risk vectors.").strip()
            clm_logger.info(f"[RiskAgent] Risk audit complete. Score: {score} | Level: {level}")
            return score, level, rationale
        except Exception as exc:
            clm_logger.error(
                f"[RiskAgent] Failed to parse risk analysis. Raw: {clean_text!r}. Error: {exc}"
            )
            # Safe default fallback
            return 30.0, "MEDIUM", "Automatic audit fallback due to structural parsing error."
