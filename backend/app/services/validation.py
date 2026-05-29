import re
from datetime import datetime
from typing import Any, Dict, List, Optional
from app.services.logger import clm_logger


class ValidationService:
    """
    ValidationService — Deterministic, cross-field validation service.
    Evaluates compliance against legal and operational rules (e.g., effective vs expiry dates,
    auto-renewal notice periods, contract values, and currencies).
    """

    def validate_contract_parameters(self, parameters: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Runs programmatic validation across the complete set of extracted parameters.
        Modifies and sets 'validation_state' and 'validation_message' in-place for each parameter.
        """
        clm_logger.info("[ValidationService] Commencing deterministic cross-field validation pass...")

        # Build parameter map for quick key lookup
        p_map = {}
        for p in parameters:
            name = (p.get("param_name") or "").strip().lower()
            p_map[name] = p

        # Helper to get normalized value
        def get_val(name: str) -> Optional[str]:
            p = p_map.get(name.lower())
            if not p:
                return None
            val = p.get("user_override") or p.get("original_extract")
            if val is not None:
                val = str(val).strip()
            return val if val else None

        # Helper to parse dates
        def parse_date(date_str: Optional[str]) -> Optional[datetime]:
            if not date_str:
                return None
            for fmt in (
                "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%Y/%m/%d",
                "%d-%b-%Y", "%d %B %Y", "%B %d, %Y", "%Y-%m-%dT%H:%M:%S"
            ):
                try:
                    return datetime.strptime(date_str, fmt)
                except ValueError:
                    continue
            # Try regex to extract standard YYYY-MM-DD
            match = re.search(r"(\d{4})-(\d{2})-(\d{2})", date_str)
            if match:
                try:
                    return datetime.strptime(match.group(0), "%Y-%m-%d")
                except ValueError:
                    pass
            return None

        # First pass: Set basic validation state based on citation presence
        for p in parameters:
            citation = p.get("citation_text")
            val = p.get("user_override") or p.get("original_extract")

            if not val and not citation:
                p["validation_state"] = "valid"
                p["validation_message"] = "Optional parameter not found in document text."
            elif val and not citation:
                p["validation_state"] = "missing_evidence"
                p["validation_message"] = "Value extracted without verified supporting citation text."
            else:
                p["validation_state"] = "valid"
                p["validation_message"] = "Extraction grounded with source citation."

        # Second pass: Cross-field rules

        # 1. Effective date must exist if expiry date exists
        eff_val = get_val("effective date") or get_val("effective_date")
        exp_val = get_val("expiry date") or get_val("expiry_date") or get_val("expiration date") or get_val("expiration_date")

        if exp_val and not eff_val:
            for name in ["effective date", "effective_date"]:
                if name in p_map:
                    p_map[name]["validation_state"] = "invalid"
                    p_map[name]["validation_message"] = "Effective date must exist when an Expiry date is defined."
            for name in ["expiry date", "expiry_date", "expiration date", "expiration_date"]:
                if name in p_map:
                    p_map[name]["validation_state"] = "invalid"
                    p_map[name]["validation_message"] = "Integrity violation: Missing corresponding Effective date."

        # 2. Expiry date must not precede Effective date
        if eff_val and exp_val:
            eff_dt = parse_date(eff_val)
            exp_dt = parse_date(exp_val)
            if eff_dt and exp_dt and exp_dt < eff_dt:
                for name in ["effective date", "effective_date", "expiry date", "expiry_date", "expiration date", "expiration_date"]:
                    if name in p_map:
                        p_map[name]["validation_state"] = "invalid"
                        p_map[name]["validation_message"] = (
                            f"Integrity violation: Expiry date ({exp_val}) is "
                            f"configured before Effective date ({eff_val})."
                        )

        # 3. Contract value must include currency
        val_val = get_val("contract value") or get_val("contract_value") or get_val("value") or get_val("price")
        if val_val:
            has_currency = any(symbol in val_val for symbol in ["$", "€", "£", "¥", "₹", "USD", "EUR", "GBP", "INR", "CAD", "AUD"])
            if not has_currency:
                for name in ["contract value", "contract_value", "value", "price"]:
                    if name in p_map:
                        p_map[name]["validation_state"] = "needs_review"
                        p_map[name]["validation_message"] = (
                            f"Value '{val_val}' contains no recognizable currency symbol or ISO code."
                        )

        # 4. Auto-renewal notice period should be present if auto-renewal is true
        auto_renew = get_val("auto renewal") or get_val("auto_renewal") or get_val("automatic renewal")
        notice_period = get_val("notice period") or get_val("renewal notice period") or get_val("notice_period")

        is_auto_renew_true = auto_renew and any(kw in auto_renew.lower() for kw in ["true", "yes", "enabled", "auto", "renew"])
        if is_auto_renew_true and not notice_period:
            for name in ["auto renewal", "auto_renewal", "automatic renewal"]:
                if name in p_map:
                    p_map[name]["validation_state"] = "needs_review"
                    p_map[name]["validation_message"] = (
                        "Auto-renewal is enabled, but no corresponding notice period has been extracted."
                    )

        clm_logger.info("[ValidationService] Cross-field validation complete.")
        return parameters
