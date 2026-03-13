"""
Text Preprocessing Pipeline
Cleans and normalises extracted text before classification.
"""

import re
import unicodedata


def preprocess(text: str, aggressive: bool = False) -> str:
    """
    Full preprocessing pipeline.

    Args:
        text: Raw extracted text
        aggressive: If True, also stem/lemmatize and remove stopwords
                    (useful for ML training, not for rules-based)
    """
    text = normalize_unicode(text)
    text = fix_ocr_artifacts(text)
    text = normalize_whitespace(text)
    text = expand_abbreviations(text)

    if aggressive:
        text = remove_stopwords(text)
        text = simple_stem(text)

    return text.strip()


def normalize_unicode(text: str) -> str:
    """Normalize unicode characters (handles OCR special chars)."""
    text = unicodedata.normalize("NFKD", text)
    # Replace non-ASCII with ASCII equivalent where possible
    text = text.encode("ascii", errors="ignore").decode("ascii")
    return text


def fix_ocr_artifacts(text: str) -> str:
    """Fix common OCR misreads."""
    replacements = {
        r"\bl\b": "1",        # lowercase L → 1 in numeric context
        r"\bO\b": "0",        # letter O → 0 in numeric context
        "\u2018|\u2019": "'",  # smart apostrophe/single quotes
        "\u201c|\u201d": '"', # smart double quotes
        r"–|—": "-",          # dashes
        r"…": "...",
        r"\f": "\n",          # form feed → newline
        r"[^\S\n]+": " ",     # collapse horizontal whitespace
    }
    for pattern, replacement in replacements.items():
        text = re.sub(pattern, replacement, text)
    return text


def normalize_whitespace(text: str) -> str:
    """Normalise line breaks and spacing."""
    # Collapse 3+ consecutive newlines to 2
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Remove trailing spaces on each line
    text = "\n".join(line.rstrip() for line in text.splitlines())
    return text


def expand_abbreviations(text: str) -> str:
    """Expand common financial/HR abbreviations for better keyword matching."""
    abbrevs = {
        r"\bHRA\b": "house rent allowance HRA",
        r"\bDA\b": "dearness allowance DA",
        r"\bTA\b": "travel allowance TA",
        r"\bPF\b": "provident fund PF",
        r"\bEPF\b": "employee provident fund EPF",
        r"\bESIC\b": "employee state insurance ESIC",
        r"\bPT\b": "professional tax PT",
        r"\bTDS\b": "tax deducted at source TDS",
        r"\bITR\b": "income tax return ITR",
        r"\bDr\b": "debit Dr",
        r"\bCr\b": "credit Cr",
    }
    for pattern, expansion in abbrevs.items():
        text = re.sub(pattern, expansion, text, flags=re.IGNORECASE)
    return text


def remove_stopwords(text: str) -> str:
    """Remove common English stopwords (aggressive mode)."""
    stopwords = {
        "the", "a", "an", "and", "or", "but", "in", "on", "at", "to",
        "for", "of", "with", "by", "from", "is", "are", "was", "were",
        "be", "been", "being", "have", "has", "had", "do", "does", "did",
        "will", "would", "shall", "should", "may", "might", "must", "can",
        "could", "not", "no", "nor", "so", "yet", "both", "either",
        "as", "if", "then", "than", "that", "this", "it", "its",
    }
    words = text.split()
    return " ".join(w for w in words if w.lower() not in stopwords)


def simple_stem(text: str) -> str:
    """Very basic suffix-stripping stemmer (no external deps)."""
    suffixes = ("ing", "tion", "ment", "ness", "ful", "less", "ible", "able", "ed", "er", "ly")
    words = text.split()
    stemmed = []
    for word in words:
        if len(word) > 6:
            for suffix in suffixes:
                if word.endswith(suffix) and len(word) - len(suffix) > 3:
                    word = word[: -len(suffix)]
                    break
        stemmed.append(word)
    return " ".join(stemmed)


def extract_key_fields(text: str) -> dict:
    """
    Extract structured fields from text for validation / enrichment.
    Useful for post-classification confirmation.
    """
    fields = {}

    # PAN number (India)
    pan = re.search(r"\b([A-Z]{5}[0-9]{4}[A-Z])\b", text)
    if pan:
        fields["pan_number"] = pan.group(1)

    # TAN number (India)
    tan = re.search(r"\b([A-Z]{4}[0-9]{5}[A-Z])\b", text)
    if tan:
        fields["tan_number"] = tan.group(1)

    # Assessment year
    ay = re.search(r"assessment\s+year\s*[:\-]?\s*(\d{4}\s*[-–]\s*\d{2,4})", text, re.IGNORECASE)
    if ay:
        fields["assessment_year"] = ay.group(1).strip()

    # Account number (generic)
    acct = re.search(r"account\s*(?:no|number|#)\s*[:\-]?\s*(\d[\d\s]{5,18}\d)", text, re.IGNORECASE)
    if acct:
        fields["account_number"] = acct.group(1).replace(" ", "")

    # Employee ID
    emp = re.search(r"emp(?:loyee)?\s*(?:id|code|no)\s*[:\-]?\s*(\w{2,15})", text, re.IGNORECASE)
    if emp:
        fields["employee_id"] = emp.group(1)

    # Month/period
    month = re.search(
        r"(?:pay\s*period|month\s*of|for\s+the\s+month\s*(?:of)?)\s*[:\-]?\s*"
        r"((?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
        r"jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
        r"(?:\s*\d{4})?)",
        text,
        re.IGNORECASE,
    )
    if month:
        fields["pay_period"] = month.group(1).strip()

    return fields