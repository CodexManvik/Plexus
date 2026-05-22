import re

def normalize_text(value: str) -> str:
    """
    Standardizes currency codes, handles scaling abbreviations (m/k/b),
    and normalizes spacing to stabilize Levenshtein text precision calculations.
    """
    if not value:
        return ""
        
    # 1. Lowercase, strip padding, and normalize all whitespaces
    text = value.strip().lower()
    text = re.sub(r"\s+", " ", text)
    
    # 2. Standardize Currency Denominations
    # Converts 'usd', 'dollars', 'dollar' or 'eur', 'euros' to unified symbols
    text = re.sub(r"\b(usd|dollars?)\b", "$", text)
    text = re.sub(r"\b(eur|euros?)\b", "€", text)
    text = re.sub(r"\b(gbp|pounds?)\b", "£", text)
    
    # Fix spacing issues like "$ 500" or "€   10,000" -> "$500", "€10,000"
    text = re.sub(r"([$,€,£])\s+", r"\1", text)
    
    # 3. Process Compact Financial Shorthand (e.g., "1.5m", "250k")
    # Matches a number followed immediately by k, m, or b
    text = re.sub(r"\b(\d+(?:\.\d+)?)\s*k\b", lambda m: str(int(float(m.group(1)) * 1000)), text)
    text = re.sub(r"\b(\d+(?:\.\d+)?)\s*m\b", lambda m: str(int(float(m.group(1)) * 1000000)), text)
    text = re.sub(r"\b(\d+(?:\.\d+)?)\s*b\b", lambda m: str(int(float(m.group(1)) * 1000000000)), text)
    
    # 4. Process Written Text Multipliers (e.g., "5 million", "12 thousand")
    multipliers = {
        "million": 1000000,
        "billion": 1000000000,
        "thousand": 1000,
    }
    def _scale_word_match(match):
        number_part = match.group(1)
        scale_word = match.group(2)
        return str(int(float(number_part) * multipliers[scale_word]))
        
    text = re.sub(r"\b(\d+(?:\.\d+)?)\s*(million|billion|thousand)\b", _scale_word_match, text)
    
    # 5. Clean Numeric Separators
    # Removes commas entirely to align "1,000,000" with "1000000"
    # If it ends with trailing zero decimals (e.g. ".00"), strip them to keep integers uniform
    text = text.replace(",", "")
    text = re.sub(r"\.00\b", "", text)
    
    return text.strip()