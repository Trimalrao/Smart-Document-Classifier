"""
Tests for the Document Classifier.
Run: python -m pytest tests/ -v
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from src.classifier import RulesBasedClassifier, CATEGORIES
from src.preprocessor import preprocess, extract_key_fields
from src.evaluator import evaluate


# ─── Sample documents ───────────────────────────────────────────────────────

BANK_STATEMENT_TEXT = """
    STATE BANK OF INDIA
    Statement of Account
    Account No: 1234567890
    IFSC Code: SBIN0001234
    
    Date       Description              Debit      Credit    Balance
    01/01/2024 Opening Balance                               10,000.00
    05/01/2024 UPI Transfer          2,000.00              8,000.00 Cr
    10/01/2024 Salary Credit                   50,000.00  58,000.00 Cr
    15/01/2024 ATM Withdrawal         5,000.00             53,000.00
    
    Closing Balance: 53,000.00
"""

PAYSLIP_TEXT = """
    PAYSLIP FOR THE MONTH OF JANUARY 2024
    
    Employee Name: John Doe
    Employee ID: EMP00123
    Department: Engineering
    Designation: Senior Developer
    PAN Number: ABCDE1234F
    
    EARNINGS                    DEDUCTIONS
    Basic Pay:     40,000       PF:              4,800
    HRA:           16,000       Professional Tax:  200
    DA:             4,000       TDS Deducted:    3,500
    Conveyance:     1,600       ESIC:              500
    
    Gross Salary:  61,600       Total Deductions: 9,000
    
    NET SALARY (Take Home): Rs. 52,600
"""

TAX_DOCUMENT_TEXT = """
    FORM 16
    CERTIFICATE UNDER SECTION 203 OF THE INCOME-TAX ACT, 1961
    
    TAN of Deductor: ABCD12345E
    PAN of Employee: ABCDE1234F
    
    Assessment Year: 2023-24
    Financial Year: 2022-23
    
    Gross Total Income:                 7,20,000
    Deductions under Chapter VI-A:
      Section 80C (PF, LIC, etc.):     1,50,000
    
    Taxable Income:                     5,70,000
    Tax Payable:                          22,500
    TDS Deducted at Source:               22,500
    
    This is a TDS Certificate issued by TRACES.
"""

OTHER_TEXT = """
    INVOICE #INV-2024-001
    
    Billing To: ABC Corp Ltd
    Invoice Date: 15 January 2024
    
    Item              Qty    Rate    Amount
    Web Development    1    50,000   50,000
    
    Sub Total: 50,000
    GST 18%:    9,000
    Total:     59,000
    
    Terms: Payment due within 30 days.
"""


# ─── Classifier tests ────────────────────────────────────────────────────────

class TestRulesBasedClassifier:
    def setup_method(self):
        self.clf = RulesBasedClassifier()

    def test_bank_statement(self):
        result = self.clf.classify(preprocess(BANK_STATEMENT_TEXT))
        assert result.label == "Bank Statement", f"Got: {result.label}"
        assert result.confidence > 0.3

    def test_payslip(self):
        result = self.clf.classify(preprocess(PAYSLIP_TEXT))
        assert result.label == "Payslip", f"Got: {result.label}"
        assert result.confidence > 0.3

    def test_tax_document(self):
        result = self.clf.classify(preprocess(TAX_DOCUMENT_TEXT))
        assert result.label == "Tax Document", f"Got: {result.label}"
        assert result.confidence > 0.3

    def test_others(self):
        result = self.clf.classify(preprocess(OTHER_TEXT))
        assert result.label == "Others"

    def test_result_has_scores(self):
        result = self.clf.classify(BANK_STATEMENT_TEXT)
        assert isinstance(result.scores, dict)
        assert len(result.scores) > 0

    def test_result_method_is_rules(self):
        result = self.clf.classify(BANK_STATEMENT_TEXT)
        assert result.method == "rules"


# ─── Preprocessor tests ──────────────────────────────────────────────────────

class TestPreprocessor:
    def test_basic_cleanup(self):
        raw = "Hello   World\n\n\n\nTest"
        processed = preprocess(raw)
        assert "   " not in processed
        assert "\n\n\n" not in processed

    def test_abbreviation_expansion(self):
        text = preprocess("Employee PF and HRA details")
        assert "provident fund" in text.lower()
        assert "house rent allowance" in text.lower()

    def test_extract_pan(self):
        fields = extract_key_fields("PAN: ABCDE1234F details here")
        assert fields.get("pan_number") == "ABCDE1234F"

    def test_extract_account_number(self):
        fields = extract_key_fields("Account No: 1234567890 at SBI")
        assert "account_number" in fields

    def test_extract_employee_id(self):
        fields = extract_key_fields("Employee ID: EMP00123")
        assert fields.get("employee_id") == "EMP00123"


# ─── Evaluator tests ─────────────────────────────────────────────────────────

class TestEvaluator:
    def test_perfect_accuracy(self):
        labels = ["Bank Statement", "Payslip", "Tax Document"]
        metrics = evaluate(labels, labels)
        assert metrics["accuracy"] == 1.0
        assert metrics["macro_f1"] == 1.0

    def test_partial_accuracy(self):
        y_true = ["Bank Statement", "Bank Statement", "Payslip"]
        y_pred = ["Bank Statement", "Payslip",       "Payslip"]
        metrics = evaluate(y_true, y_pred)
        assert metrics["accuracy"] == pytest.approx(2/3, abs=0.01)

    def test_confusion_matrix_populated(self):
        y_true = ["Bank Statement", "Payslip"]
        y_pred = ["Payslip",        "Payslip"]
        metrics = evaluate(y_true, y_pred)
        assert metrics["confusion_matrix"]["Bank Statement"]["Payslip"] == 1

    def test_per_class_keys(self):
        labels = ["Bank Statement", "Payslip"]
        metrics = evaluate(labels, labels)
        for label in ["Bank Statement", "Payslip"]:
            assert "precision" in metrics["per_class"][label]
            assert "recall" in metrics["per_class"][label]
            assert "f1" in metrics["per_class"][label]


if __name__ == "__main__":
    # Quick smoke test without pytest
    clf = RulesBasedClassifier()
    for name, text in [
        ("Bank Statement", BANK_STATEMENT_TEXT),
        ("Payslip", PAYSLIP_TEXT),
        ("Tax Document", TAX_DOCUMENT_TEXT),
        ("Other (Invoice)", OTHER_TEXT),
    ]:
        result = clf.classify(preprocess(text))
        status = "✓" if result.label == name or (name.startswith("Other") and result.label == "Others") else "✗"
        print(f"{status} {name:<20} → {result.label:<20} (confidence={result.confidence:.2%})")
