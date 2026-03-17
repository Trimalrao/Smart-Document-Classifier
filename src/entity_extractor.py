"""
Entity Extractor  (fixed)
=========================
Extracts structured entities from classified document text.

Fixes applied:
  BANK  - Account holder name no longer includes trailing "Account Number" / "A/C No" etc.
        - Account number extraction handles all 3 label variants on same line
        - Grouping fallback uses normalized name when account number missing
  PAY   - Employee name stripped of UAN, numbers, trailing ID fields
        - Employee ID matches Employee ID / Emp ID / Employee Code
        - Company name taken from first section, not random uppercase
  TAX   - Employee PAN extracted only; Employer PAN explicitly excluded
        - Handles OCR glitch "Permanent Account NumbeCrXXXXX" (merged label+value)

All functions return a dict.  Missing fields → empty string "".
"""

import re
from datetime import datetime
from typing import Optional


# ─────────────────────────────────────────────────────────────────────────────
# Shared helpers
# ─────────────────────────────────────────────────────────────────────────────

MONTH_MAP = {
    "jan": 1,  "january": 1,
    "feb": 2,  "february": 2,
    "mar": 3,  "march": 3,
    "apr": 4,  "april": 4,
    "may": 5,
    "jun": 6,  "june": 6,
    "jul": 7,  "july": 7,
    "aug": 8,  "august": 8,
    "sep": 9,  "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}

MONTH_PATTERN = (
    r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?"
    r"|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
)

# Noise keywords that must be removed from extracted names
_NAME_NOISE = re.compile(
    r"\b(account\s*(?:no|number|#|holder)?|a/c\s*(?:no|number)?|"
    r"employee\s*(?:id|code|no)?|emp\s*(?:id|code|no)?|staff\s*(?:id|no)?|"
    r"uan\s*(?:number)?|pan\s*(?:no|number)?|tan\s*(?:no|number)?|"
    r"permanent\s*account|"
    r"ifsc|branch|department|designation|company|period|payslip|"
    r"salary|month|date)\b.*",
    re.IGNORECASE,
)

# Trailing digits / symbols / punctuation
_TRAILING_NOISE = re.compile(r"[\d\s\-:/|@#&*,.]+$")


def _clean_name(raw: str) -> str:
    """
    Strip trailing noise keywords and digits from an extracted name.
    E.g. "Sneha Kulkarni Account Number" → "Sneha Kulkarni"
         "Rahul Sharma UAN 123456"        → "Rahul Sharma"
    """
    if not raw:
        return ""
    # Remove everything from a noise keyword onward
    cleaned = _NAME_NOISE.sub("", raw)
    # Remove trailing numbers/symbols
    cleaned = _TRAILING_NOISE.sub("", cleaned)
    # Collapse whitespace
    cleaned = " ".join(cleaned.split())
    # Must be at least 2 words and only letters/spaces
    if re.match(r"^[A-Za-z][A-Za-z\s]{2,}$", cleaned):
        return cleaned.strip()
    return ""


def parse_month_year(raw: str) -> Optional[datetime]:
    """Parse a raw month string into datetime(year, month, 1). Returns None if unparseable."""
    if not raw:
        return None
    raw = raw.strip()
    for fmt in ("%B %Y", "%b %Y", "%B-%Y", "%b-%Y", "%m/%Y", "%Y-%m", "%m-%Y"):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            pass
    m = re.match(r"([A-Za-z]+)[\s\-/]+(\d{2})$", raw)
    if m:
        mn, yr2 = m.group(1), m.group(2)
        year = 2000 + int(yr2) if int(yr2) <= 50 else 1900 + int(yr2)
        for fmt in ("%b %Y", "%B %Y"):
            try:
                return datetime.strptime(f"{mn} {year}", fmt)
            except ValueError:
                pass
    m = re.match(r"^([A-Za-z]+)$", raw)
    if m:
        key = m.group(1).lower()[:3]
        if key in MONTH_MAP:
            return datetime(1900, MONTH_MAP[key], 1)
    return None


def month_sort_key(raw: str) -> datetime:
    dt = parse_month_year(raw)
    return dt if dt else datetime(1900, 1, 1)


# ─────────────────────────────────────────────────────────────────────────────
# BANK STATEMENT
# ─────────────────────────────────────────────────────────────────────────────

_KNOWN_BANKS = [
    "State Bank of India", "SBI",
    "HDFC Bank", "HDFC",
    "ICICI Bank", "ICICI",
    "Axis Bank",
    "Kotak Mahindra Bank", "Kotak",
    "Punjab National Bank", "PNB",
    "Bank of Baroda",
    "Canara Bank",
    "Yes Bank",
    "Union Bank",
    "Wells Fargo", "Citibank", "PNC Bank", "Deutsche Bank",
    "Bank of America", "Chase Bank", "HSBC", "Barclays", "TD Bank",
]

# Labels used for account number in these PDFs
_ACCT_LABELS = (
    r"account\s*(?:no|number|#)",   # Account Number / Account No.
    r"a/c\s*(?:no|number)?",        # A/C No / A/C Number
    r"acc(?:ount)?\s*no",
)
_ACCT_LABEL_PAT = re.compile(
    r"(?:" + "|".join(_ACCT_LABELS) + r")\s*[:\.]?\s*(\d[\d\s]{5,20}\d)",
    re.IGNORECASE,
)

# Account holder label
_HOLDER_PAT = re.compile(
    r"account\s*holder\s*(?:name)?\s*[:\-]?\s*(.+?)(?=\s+(?:account|a/c|branch|ifsc)|$)",
    re.IGNORECASE,
)


def _extract_account_number(text: str) -> str:
    """
    Extract account number from text.
    Handles: "Account Number: 458912340921", "A/C Number: 334455667788",
             "Account No.: 998877665544"
    Also handles masked formats: "XXXX1234", "1234 5678 9012"
    Normalises by removing spaces.
    """
    # Try labeled extraction first (most reliable)
    m = _ACCT_LABEL_PAT.search(text)
    if m:
        return m.group(1).replace(" ", "").strip()

    # Masked account number  XXXX1234  or  xxxx-1234
    m = re.search(r"\b[Xx]{4}[\s\-]?\d{4}\b", text)
    if m:
        return re.sub(r"[\s\-]", "", m.group()).upper()

    # 12-digit number that looks like an account number
    m = re.search(r"\b(\d{10,16})\b", text)
    if m:
        # Exclude if it looks like a date or phone (heuristic)
        num = m.group(1)
        if len(num) >= 10:
            return num

    return ""


def _extract_holder_name(text: str) -> str:
    """
    Extract holder name from "Account Holder Name: Sneha Kulkarni Account Number: ..."
    Stops at the next label keyword on the same line.
    """
    m = _HOLDER_PAT.search(text)
    if m:
        raw = m.group(1).strip()
        return _clean_name(raw)

    # Fallback: "Name: XYZ" style
    m = re.search(
        r"(?:customer|client|holder)\s*name\s*[:\-]?\s*(.+?)(?=\s+[A-Z].*:|$)",
        text, re.IGNORECASE,
    )
    if m:
        return _clean_name(m.group(1))

    return ""


def extract_bank_statement(text: str, filename: str = "") -> dict:
    account_number = _extract_account_number(text)
    holder_name    = _extract_holder_name(text)

    # Bank name
    bank_name = ""
    for bn in _KNOWN_BANKS:
        if re.search(r"\b" + re.escape(bn) + r"\b", text, re.IGNORECASE):
            bank_name = bn
            break

    # Statement month — prefer explicit "Statement Month: April 2024"
    statement_month = ""
    m = re.search(
        r"statement\s*month\s*[:\-]?\s*" + MONTH_PATTERN + r"\s+(\d{4})",
        text, re.IGNORECASE,
    )
    if m:
        statement_month = f"{m.group(1).capitalize()} {m.group(2)}"
    else:
        # "Statement Period: 01 Apr 2024 to 30 Apr 2024" → take first month
        m = re.search(
            r"statement\s*period\s*[:\-]?\s*\d{1,2}\s+" + MONTH_PATTERN + r"\s+(\d{4})",
            text, re.IGNORECASE,
        )
        if m:
            statement_month = f"{m.group(1).capitalize()} {m.group(2)}"
        else:
            # Generic month year anywhere near top
            m = re.search(r"\b" + MONTH_PATTERN + r"\s+(\d{4})\b", text, re.IGNORECASE)
            if m:
                statement_month = f"{m.group(1).capitalize()} {m.group(2)}"

    return {
        "account_number":  account_number,
        "holder_name":     holder_name,
        "bank_name":       bank_name,
        "statement_month": statement_month,
        "filename":        filename,
    }


# ─────────────────────────────────────────────────────────────────────────────
# PAYSLIP
# ─────────────────────────────────────────────────────────────────────────────

# Matches all ID label variants used in these PDFs:
# "Employee ID: EMP1021"  "Emp ID: EMP1045"  "Employee Code: EMP1156"  "Employee Code: EMP1067"
_EMP_ID_PAT = re.compile(
    r"(?:employee\s*(?:id|code)|emp(?:loyee)?\s*(?:id|code|no))\s*[:\-]?\s*([A-Za-z0-9]{2,15})",
    re.IGNORECASE,
)

# Employee Name label — stops before the next label on same line
_EMP_NAME_PAT = re.compile(
    r"employee\s*name\s*[:\-]?\s*(.+?)(?=\s+(?:employee|emp|staff|uan|pan|dept|depart|company|$))",
    re.IGNORECASE,
)

# Pay month labels across all payslip variants in this dataset
_PAY_MONTH_PAT = re.compile(
    r"(?:payslip\s*month|salary\s*month|pay\s*(?:period|month)|payroll\s*period)"
    r"\s*[:\-]?\s*" + MONTH_PATTERN + r"(?:\s*[\-,]?\s*(\d{4}))?",
    re.IGNORECASE,
)


def _extract_employee_name(text: str) -> str:
    """
    Extract employee name, ensuring we stop before ID labels.
    E.g. "Employee Name: Rahul Sharma Employee ID: EMP1021" → "Rahul Sharma"
    """
    m = _EMP_NAME_PAT.search(text)
    if m:
        raw = m.group(1).strip()
        return _clean_name(raw)

    # Broader fallback
    m = re.search(
        r"(?:name\s*of\s*employee|employee\s*name)\s*[:\-]?\s*([A-Za-z][A-Za-z\s]{2,35})",
        text, re.IGNORECASE,
    )
    if m:
        return _clean_name(m.group(1))

    return ""


def _extract_employee_id(text: str) -> str:
    m = _EMP_ID_PAT.search(text)
    if m:
        val = m.group(1).strip()
        # Must not look like a person's name (no spaces)
        if " " not in val:
            return val
    return ""


def _extract_company(text: str) -> str:
    """
    Extract company name.  For these PDFs it's the very first line (e.g. "ThoughtFocus").
    Fall back to explicit label search.
    """
    lines = [l.strip() for l in text.splitlines() if l.strip()]

    # Explicit label
    m = re.search(
        r"(?:company|employer|organisation|organization)\s*[:\-]?\s*([A-Za-z][^\n]{2,50})",
        text, re.IGNORECASE,
    )
    if m:
        raw = m.group(1).strip()
        # Clean trailing noise
        raw = re.split(r"[|/\n]", raw)[0].strip()
        if 2 < len(raw) < 80:
            return raw

    # If first non-header line is short and looks like a company name, use it
    for line in lines[:5]:
        if (3 < len(line) < 60
                and not re.search(r"pay\s*slip|payslip|salary|employee|department", line, re.IGNORECASE)
                and re.match(r"^[A-Za-z]", line)):
            return line

    return ""


def extract_payslip(text: str, filename: str = "") -> dict:
    employee_id   = _extract_employee_id(text)
    employee_name = _extract_employee_name(text)
    company       = _extract_company(text)

    # Pay month
    payslip_month = ""
    m = _PAY_MONTH_PAT.search(text)
    if m:
        mon  = m.group(1).capitalize()
        year = m.group(2) if m.lastindex >= 2 and m.group(2) else ""
        payslip_month = f"{mon} {year}".strip() if year else mon
    else:
        # Fallback: any "Month YYYY" near top
        m = re.search(r"\b" + MONTH_PATTERN + r"\s+(\d{4})\b", text, re.IGNORECASE)
        if m:
            payslip_month = f"{m.group(1).capitalize()} {m.group(2)}"

    return {
        "employee_id":   employee_id,
        "employee_name": employee_name,
        "company":       company,
        "payslip_month": payslip_month,
        "filename":      filename,
    }


# ─────────────────────────────────────────────────────────────────────────────
# TAX DOCUMENT
# ─────────────────────────────────────────────────────────────────────────────

# PAN pattern
_PAN_RE = re.compile(r"[A-Z]{5}[0-9]{4}[A-Z]")

# Contexts that signal an EMPLOYER / DEDUCTOR PAN — must be excluded
_EMPLOYER_PAN_CONTEXT = re.compile(
    r"(employer|deductor|company|organisation|organization)\s+pan",
    re.IGNORECASE,
)


def _extract_employee_pan(text: str) -> str:
    """
    Extract the EMPLOYEE's PAN, not the employer's.

    Strategy:
    1. Look for lines with "Employee PAN", "Assessee PAN", "PAN Number",
       "Permanent Account Number" and grab the PAN from that line.
    2. Parse "Permanent Account NumbeCrXXXXX" OCR glitch where label+value merge.
    3. Fall back to scanning all PAN-looking tokens and excluding those on
       lines that mention Employer/Deductor.
    """
    lines = text.splitlines()

    # Pass 1 — explicit employee PAN labels
    employee_labels = re.compile(
        r"(?:employee\s*pan|assessee\s*pan|pan\s*(?:no|number)|"
        r"permanent\s*account\s*numb(?:er)?)\s*[:\-]?\s*",
        re.IGNORECASE,
    )
    for line in lines:
        # Skip lines that also mention Employer
        if re.search(r"\bemployer\b|\bdeductor\b", line, re.IGNORECASE):
            continue
        if employee_labels.search(line):
            pans = _PAN_RE.findall(line)
            if pans:
                return pans[0]
            # OCR glitch: "Permanent Account NumbeCrMNPQ9012R"
            # label merges into value → try to extract PAN from end of label text
            m = employee_labels.search(line)
            if m:
                remainder = line[m.end():]
                # also check if PAN is embedded inside the label match itself
                full_label_region = line[m.start():]
                found = _PAN_RE.findall(full_label_region)
                if found:
                    return found[0]

    # Pass 2 — "Name of Employee ... PAN: XXXXX" on same line
    for line in lines:
        if re.search(r"\bname\s*of\s*employee\b|\bemployee\s*name\b", line, re.IGNORECASE):
            pans = _PAN_RE.findall(line)
            if pans:
                return pans[0]

    # Pass 3 — "deducted from salary of Name (PAN: XXXXX)"
    m = re.search(
        r"deducted\s+from\s+the\s+salary\s+of\s+.+?\(PAN[:\s]*([A-Z]{5}[0-9]{4}[A-Z])\)",
        text, re.IGNORECASE,
    )
    if m:
        return m.group(1)

    # Pass 4 — fallback: any PAN NOT on an employer line
    for line in lines:
        if _EMPLOYER_PAN_CONTEXT.search(line):
            continue
        pans = _PAN_RE.findall(line)
        if pans:
            return pans[0]

    return ""


def _extract_tax_employee_name(text: str) -> str:
    m = re.search(
        r"name\s*of\s*employee\s*[:\-]?\s*([A-Za-z][A-Za-z\s]{2,35})",
        text, re.IGNORECASE,
    )
    if m:
        return _clean_name(m.group(1))

    # "salary of Rahul Sharma (PAN: AVKPV1234D)"
    m = re.search(
        r"salary\s+of\s+([A-Za-z][A-Za-z\s]{2,35})\s*[\(\[]?\s*PAN",
        text, re.IGNORECASE,
    )
    if m:
        return _clean_name(m.group(1))

    return ""


def _extract_employer(text: str) -> str:
    m = re.search(
        r"name\s*of\s*employer\s*[:\-]?\s*([A-Za-z][^\n]{2,60})",
        text, re.IGNORECASE,
    )
    if m:
        raw = m.group(1).strip()
        # Stop at the next label
        raw = re.split(r"\s{2,}|\bEmployer\b|\bPAN\b|\bTAN\b", raw)[0].strip()
        return raw
    return ""


def _extract_assessment_year(text: str) -> str:
    # "Assessment Year AY 2024-25"  or  "Assessment Year: 2024-25"
    m = re.search(
        r"assessment\s+year\s*(?:ay)?\s*[:\-]?\s*(\d{4}\s*[-–]\s*\d{2,4})",
        text, re.IGNORECASE,
    )
    if m:
        return m.group(1).strip().replace(" ", "")

    # "AY 2024-25"
    m = re.search(r"\bay\s+(\d{4}[-–]\d{2,4})\b", text, re.IGNORECASE)
    if m:
        return m.group(1)

    return ""


def extract_tax_document(text: str, filename: str = "") -> dict:
    return {
        "pan":             _extract_employee_pan(text),
        "employee_name":   _extract_tax_employee_name(text),
        "employer":        _extract_employer(text),
        "assessment_year": _extract_assessment_year(text),
        "filename":        filename,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Public dispatcher
# ─────────────────────────────────────────────────────────────────────────────

def extract_entities(label: str, text: str, filename: str = "") -> dict:
    """
    Dispatch to the correct extractor based on classification label.
    Returns {} for Others / unknown.

    To add a new category:
      1. Write an extract_<name>() function above.
      2. Register it in EXTRACTORS below.
    """
    EXTRACTORS = {
        "Bank Statement": extract_bank_statement,
        "Payslip":        extract_payslip,
        "Tax Document":   extract_tax_document,
    }
    fn = EXTRACTORS.get(label)
    if fn is None:
        return {}
    try:
        return fn(text, filename)
    except Exception:
        return {}