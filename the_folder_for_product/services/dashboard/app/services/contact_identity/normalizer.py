import re

def normalize_phone(raw_phone: str, default_country: str = "IN") -> str:
    """
    Normalizes phone numbers to standard E.164 format.
    Specialized for Indian numbers with fallback for international numbers:
    - 9876543210 -> +919876543210
    - 09876543210 -> +919876543210
    - 919876543210 -> +919876543210
    - +91 98765 43210 -> +919876543210
    """
    if not raw_phone:
        return ""

    # Strip whitespace, hyphens, parentheses, dots
    cleaned = re.sub(r"[\s\-\(\)\.]", "", str(raw_phone).strip())

    if not cleaned:
        return ""

    # Check if already starts with +
    if cleaned.startswith("+"):
        # Strip any redundant zeroes e.g. +9109876543210 -> +919876543210
        if cleaned.startswith("+910") and len(cleaned) == 14:
            cleaned = "+91" + cleaned[4:]
        return cleaned

    # Check for Indian number patterns
    if default_country == "IN":
        # 10 digits starting with 6, 7, 8, 9
        if len(cleaned) == 10 and cleaned[0] in "6789":
            return f"+91{cleaned}"
        # 11 digits starting with 0 followed by 6, 7, 8, 9
        if len(cleaned) == 11 and cleaned.startswith("0") and cleaned[1] in "6789":
            return f"+91{cleaned[1:]}"
        # 12 digits starting with 91
        if len(cleaned) == 12 and cleaned.startswith("91") and cleaned[2] in "6789":
            return f"+{cleaned}"

    # Generic fallback: prefix '+' if valid digits
    if re.match(r"^\d{7,15}$", cleaned):
        return f"+{cleaned}"

    return cleaned
