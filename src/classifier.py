"""
Document Content Classifier
Categories: Bank Statement, Payslip, Tax Document, Others
"""

import re
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class ClassificationResult:
    label: str
    confidence: float
    method: str
    scores: dict = field(default_factory=dict)
    reasoning: list = field(default_factory=list)


CATEGORIES = {

    # ── Bank Statement ─────────────────────────────────────────────────────
    "bank_statement": {
        "label": "Bank Statement",
        "keywords": [
            # Indian bank keywords
            "bank statement", "statement of account", "account statement",
            "opening balance", "closing balance", "available balance",
            "transaction date", "ifsc code", "swift code", "iban",
            "cheque number", "passbook", "savings account", "current account",
            "mini statement", "account summary",
            # US / international bank keywords
            "monthly statement", "fdic insured", "fdic",
            "atm withdrawal", "direct deposit",
            "interest credit", "online transfer",
            "wells fargo", "citibank", "bank of america",
            "chase bank", "pnc bank", "deutsche bank",
            "hsbc", "barclays", "td bank",
        ],
        "patterns": [
            r"account\s*[:\*#][\s\*\d]{4,}",          # account: **** **** **** 6198
            r"(opening|closing)\s*[:\-]\s*[\$₹£€]?[\d,]+\.\d{2}",  # Opening: $2,465.44
            r"(opening|closing)\s+balance\s*[:\-]?\s*[\$₹£€]?[\d,]+\.\d{2}",
            r"\b(ifsc|swift|iban|fdic)\b",
            r"balance\s*(b/f|c/f|carried forward|brought forward)",
            # transaction row: date + description + amount + balance
            r"\b\d{2}[\/\-]\d{2}[\/\-]\d{4}\s+.{3,45}\s+[\d,]+\.\d{2}",
            r"(debit|credit)\s+balance",
            r"atm\s+withdrawal",
            r"monthly\s+statement",
        ],
        "negative_keywords": ["form 16", "payslip", "salary slip"],
        "weight": 1.0,
    },

    # ── Payslip ────────────────────────────────────────────────────────────
    "payslip": {
        "label": "Payslip",
        "keywords": [
            "payslip", "pay slip", "salary slip", "salary statement",
            "employee name", "employee id", "employee code",
            "basic salary", "basic pay", "gross salary", "gross pay",
            "net salary", "net pay", "take home", "in-hand salary",
            "house rent allowance", "dearness allowance",
            "provident fund", "professional tax",
            "tds deducted", "earnings", "deductions",
            "pay period", "month of salary", "salary for the month",
            "department", "designation",
        ],
        "patterns": [
            r"(employee|emp)\s*(id|code|no\.?)\s*[:\-]\s*\w+",
            r"(basic|gross|net)\s+(salary|pay|wages)\s*[:\-]?\s*[\$₹£€]?[\d,]+",
            r"house\s+rent\s+allowance",
            r"dearness\s+allowance",
            r"provident\s+fund\s*(deduction|contribution)?",
            r"pay\s+(period|for\s+the\s+month)",
            r"(earnings|deductions)\s+total\s*[:\-]?\s*[\$₹£€]?[\d,]+",
        ],
        "negative_keywords": ["bank statement", "form 16"],
        "weight": 1.0,
    },

    # ── Tax Document ───────────────────────────────────────────────────────
    "tax_document": {
        "label": "Tax Document",
        "keywords": [
            "form 16", "form 16a", "form 26as", "tds certificate",
            "income tax", "assessment year", "financial year",
            "tan number", "tax deducted at source",
            "gross total income", "taxable income", "tax payable",
            "advance tax", "self assessment tax",
            "income tax return", "section 80c", "section 80d",
            "deduction under chapter vi", "traces",
        ],
        "patterns": [
            r"\bform\s*16[ab]?\b",
            r"(assessment|financial)\s+year\s+\d{4}[\-\/]\d{2,4}",
            r"\btan\s*(no\.?|number)?\s*[:\-]\s*[A-Z]{4}\d{5}[A-Z]",
            r"\bpan\s*(no\.?|number)?\s*[:\-]\s*[A-Z]{5}\d{4}[A-Z]",
            r"\b(section|u/s)\s*80[a-zA-Z]+",
            r"(gross\s+total|taxable)\s+income",
            r"tds\s*(deducted|certificate|details)",
        ],
        "negative_keywords": ["payslip", "salary slip", "bank statement"],
        "weight": 1.0,
    },

    # ── Others (fallback) ──────────────────────────────────────────────────
    "others": {
        "label": "Others",
        "keywords": [],
        "patterns": [],
        "negative_keywords": [],
        "weight": 0.0,
    },
}

REASON_TEMPLATES = {
    "Bank Statement": "Detected bank account transactions, balance entries, and account identifiers.",
    "Payslip":        "Detected salary components, employee details, and pay period information.",
    "Tax Document":   "Detected tax forms, TDS details, assessment year, and income declarations.",
    "Others":         "Could not match any known document category based on content.",
}


# ── Scoring ────────────────────────────────────────────────────────────────

def _score_category(text: str, category_key: str) -> tuple[float, list]:
    cat = CATEGORIES[category_key]
    if category_key == "others":
        return 0.0, []

    text_lower = text.lower()
    score      = 0.0
    reasoning  = []

    # Keyword matching with word-boundary for single words
    keyword_hits = []
    for kw in cat["keywords"]:
        if " " in kw:
            if kw in text_lower:
                keyword_hits.append(kw)
        else:
            if re.search(r"\b" + re.escape(kw) + r"\b", text_lower):
                keyword_hits.append(kw)

    if keyword_hits:
        kw_score = min(len(keyword_hits) * 0.12, 0.65)
        score   += kw_score
        reasoning.append(f"Keywords matched ({len(keyword_hits)}): {keyword_hits[:6]}")

    # Pattern matching
    pattern_hits = []
    for pat in cat["patterns"]:
        if re.search(pat, text_lower, re.IGNORECASE):
            pattern_hits.append(pat[:50])
            score += 0.18

    if pattern_hits:
        reasoning.append(f"Patterns matched ({len(pattern_hits)})")

    # Negative keyword penalty
    neg_hits = []
    for nk in cat["negative_keywords"]:
        if " " in nk:
            if nk in text_lower:
                neg_hits.append(nk)
        else:
            if re.search(r"\b" + re.escape(nk) + r"\b", text_lower):
                neg_hits.append(nk)

    if neg_hits:
        score -= 0.35
        reasoning.append(f"Negative keywords reduced score: {neg_hits}")

    return round(score * cat["weight"], 4), reasoning


# ── Classifiers ────────────────────────────────────────────────────────────

class RulesBasedClassifier:
    CONFIDENCE_THRESHOLD = 0.20

    def classify(self, text: str) -> ClassificationResult:
        scores        = {}
        all_reasoning = {}

        for cat_key in CATEGORIES:
            if cat_key == "others":
                continue
            score, reasoning      = _score_category(text, cat_key)
            scores[cat_key]       = score
            all_reasoning[cat_key] = reasoning

        best_cat   = max(scores, key=scores.get)
        best_score = scores[best_cat]

        if best_score < self.CONFIDENCE_THRESHOLD:
            return ClassificationResult(
                label="Others",
                confidence=round(1.0 - best_score, 4),
                method="rules",
                scores=scores,
                reasoning=["No category scored above threshold — classified as Others"],
            )

        min_score  = min(scores.values())
        shifted    = {k: v - min_score for k, v in scores.items()}
        total      = sum(shifted.values()) or 1
        confidence = round(shifted[best_cat] / total, 4)

        return ClassificationResult(
            label=CATEGORIES[best_cat]["label"],
            confidence=min(confidence, 0.99),
            method="rules",
            scores=scores,
            reasoning=all_reasoning.get(best_cat, []),
        )


class MLClassifier:
    def __init__(self):
        from sklearn.pipeline import Pipeline
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.linear_model import LogisticRegression
        self.pipeline = Pipeline([
            ("tfidf", TfidfVectorizer(max_features=10000, ngram_range=(1, 2),
                                      sublinear_tf=True, stop_words="english")),
            ("clf",   LogisticRegression(max_iter=1000, C=1.0, class_weight="balanced")),
        ])
        self.trained = False

    def train(self, texts, labels):
        self.pipeline.fit(texts, labels)
        self.trained = True

    def save(self, path):
        import joblib; joblib.dump(self.pipeline, path)

    def load(self, path):
        import joblib; self.pipeline = joblib.load(path); self.trained = True

    def classify(self, text: str) -> ClassificationResult:
        if not self.trained:
            raise RuntimeError("MLClassifier must be trained before use.")
        proba   = self.pipeline.predict_proba([text])[0]
        classes = self.pipeline.classes_
        best    = classes[proba.argmax()]
        return ClassificationResult(
            label=best, confidence=round(float(proba.max()), 4),
            method="ml", scores=dict(zip(classes, proba.tolist())),
        )


class EnsembleClassifier:
    def __init__(self, rules_weight=0.4, ml_weight=0.6):
        self.rules        = RulesBasedClassifier()
        self.ml: Optional[MLClassifier] = None
        self.rules_weight = rules_weight
        self.ml_weight    = ml_weight

    def set_ml_classifier(self, ml: MLClassifier):
        self.ml = ml

    def classify(self, text: str) -> ClassificationResult:
        rules_result = self.rules.classify(text)
        if self.ml is None or not self.ml.trained:
            return rules_result
        ml_result  = self.ml.classify(text)
        all_labels = set(rules_result.scores) | set(ml_result.scores)
        combined   = {
            lbl: self.rules_weight * rules_result.scores.get(lbl, 0.0)
                 + self.ml_weight  * ml_result.scores.get(lbl, 0.0)
            for lbl in all_labels
        }
        best_label = max(combined, key=combined.get)
        total      = sum(combined.values()) or 1
        return ClassificationResult(
            label=best_label,
            confidence=round(combined[best_label] / total, 4),
            method="ensemble", scores=combined,
            reasoning=rules_result.reasoning,
        )