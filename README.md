# 🔍 DocSense — Document Content Classifier

> Automatically classify PDF documents into **Bank Statement**, **Payslip**, **Tax Document**, or **Others** — then extract structured entities and generate a grouped Excel summary report. No manual labelling required.

---

## Table of Contents

1. [What It Does](#1-what-it-does)
2. [Quick Start](#2-quick-start)
3. [Folder Structure](#3-folder-structure)
4. [System Architecture](#4-system-architecture)
5. [Pipeline — Step by Step](#5-pipeline--step-by-step)
6. [Module Reference](#6-module-reference)
7. [Classification Logic Deep Dive](#7-classification-logic-deep-dive)
8. [Entity Extraction Deep Dive](#8-entity-extraction-deep-dive)
9. [Excel Report Format](#9-excel-report-format)
10. [Web UI — app.py](#10-web-ui--apppy)
11. [Batch CLI — main.py](#11-batch-cli--mainpy)
12. [Supported File Types](#12-supported-file-types)
13. [Output Categories](#13-output-categories)
14. [Accuracy & Test Results](#14-accuracy--test-results)
15. [Known Issues Fixed](#15-known-issues-fixed)
16. [Adding New Categories](#16-adding-new-categories)
17. [Dependencies](#17-dependencies)
18. [Future Improvements](#18-future-improvements)

---

## 1. What It Does

DocSense reads the **text content** of a PDF document — not its filename — and:

1. **Classifies** it into one of four categories: Bank Statement, Payslip, Tax Document, or Others
2. **Extracts** structured entities (account numbers, employee IDs, PAN numbers, dates, etc.)
3. **Groups** documents by unique identifier (account number, employee ID, or PAN)
4. **Generates** a styled Excel report with one sheet per category summarising each unique person/account and their latest document

It handles both **Indian** financial documents (HDFC, SBI, Axis, EPFO, Form 16) and **international** formats (Wells Fargo, Citibank, Deutsche Bank).

---

## 2. Quick Start

```bash
# 1. Install dependencies
cd docsense
pip install -r requirements.txt

# 2a. Web interface — drag and drop in browser
python app.py
# Open http://localhost:5000

# 2b. Batch processing — classify an entire folder
# Set INPUT_PATH in main.py, then:
python main.py
```

Two output files are generated automatically when processing a folder:
- `results.json` — raw classification output for every file
- `document_summary.xlsx` — grouped Excel report (Bank Statements / Payslips / Tax Documents)

> **Anthropic API Key** — required only for scanned PDFs and image files (Claude Vision OCR).
> Set environment variable: `ANTHROPIC_API_KEY=sk-ant-...`

---

## 3. Folder Structure

```
docsense/
│
├── app.py                    ← Flask web server  (python app.py)
├── main.py                   ← Batch CLI  (set INPUT_PATH, then python main.py)
├── requirements.txt          ← Python dependencies
│
├── src/                      ← All business logic
│   ├── __init__.py
│   ├── classifier.py         ← Rules-based + ML + Ensemble classifiers
│   ├── entity_extractor.py   ← Structured field extraction per category
│   ├── evaluator.py          ← Accuracy metrics (precision / recall / F1)
│   ├── extractor.py          ← Text extraction from PDF / image / text files
│   ├── pipeline.py           ← Orchestrates all steps end-to-end
│   ├── preprocessor.py       ← Text cleaning and abbreviation expansion
│   └── report_generator.py   ← Groups results and writes Excel report
│
├── static/
│   └── css/style.css         ← DocSense dark-theme UI styles
│
├── templates/
│   └── index.html            ← Web UI (drag-and-drop interface)
│
└── data/                     ← Put your PDFs here
```

> Every piece of classification logic lives inside `src/`. Both `app.py` (web) and `main.py` (CLI) are thin wrappers that call `src/pipeline.py`.

---

## 4. System Architecture

```
USER INTERFACES
│
├── Web Browser ──→ POST /classify ──→ app.py
└── Terminal    ──→ python main.py ──→ main.py
                            │
              ┌─────────────▼──────────────┐
              │  DocumentClassificationPipeline  │
              │       src/pipeline.py       │
              └─────────────┬──────────────┘
                            │
       ┌────────────────────▼────────────────────┐
       │  STEP 1 — TEXT EXTRACTION                │
       │  src/extractor.py                        │
       │  PDF → pdfplumber → PyMuPDF → Claude Vision │
       │  Image → Claude Vision API               │
       │  TXT → utf-8 / latin-1 read              │
       └────────────────────┬────────────────────┘
                            │  raw text
       ┌────────────────────▼────────────────────┐
       │  STEP 2 — PREPROCESSING                  │
       │  src/preprocessor.py                     │
       │  unicode normalise · fix OCR artifacts   │
       │  expand abbreviations (HRA, TDS, PF...)  │
       └────────────────────┬────────────────────┘
                            │  cleaned text
       ┌────────────────────▼────────────────────┐
       │  STEP 3 — CLASSIFICATION                  │
       │  src/classifier.py                        │
       │  Score vs bank_statement                  │
       │  Score vs payslip                         │
       │  Score vs tax_document                    │
       │  Best score ≥ 0.20 → label / else Others  │
       └────────────────────┬────────────────────┘
                            │  label + confidence
       ┌────────────────────▼────────────────────┐
       │  STEP 4 — FIELD EXTRACTION               │
       │  src/preprocessor.py                     │
       │  PAN · TAN · Account No · Employee ID    │
       └────────────────────┬────────────────────┘
                            │          (batch mode only)
       ┌────────────────────▼────────────────────┐
       │  STEP 5 — ENTITY EXTRACTION              │
       │  src/entity_extractor.py                 │
       │  Bank  → account number, holder name     │
       │  Pay   → employee ID, name, company      │
       │  Tax   → PAN, employer, assessment year  │
       └────────────────────┬────────────────────┘
                            │
       ┌────────────────────▼────────────────────┐
       │  STEP 6 — GROUP + EXCEL REPORT           │
       │  src/report_generator.py                 │
       │  Group by account / emp ID / PAN         │
       │  Find latest doc per group               │
       │  Write document_summary.xlsx             │
       └─────────────────────────────────────────┘
```

---

## 5. Pipeline — Step by Step

### Step 1 — Text Extraction (`src/extractor.py`)

| Input | Method | Fallback 1 | Fallback 2 |
|---|---|---|---|
| Digital PDF | pdfplumber | PyMuPDF | Claude Vision API |
| Scanned PDF | PyMuPDF (render PNG) | Claude Vision API | — |
| Image (JPG/PNG/BMP/TIFF) | Claude Vision API | — | — |
| Plain text | UTF-8 | latin-1 | cp1252 |

If pdfplumber returns fewer than 50 characters the file is treated as scanned and escalated to Claude Vision. No Tesseract installation required.

### Step 2 — Preprocessing (`src/preprocessor.py`)

| Function | What it does |
|---|---|
| `normalize_unicode()` | Strips non-ASCII, normalises NFKD encoding |
| `fix_ocr_artifacts()` | Replaces smart quotes, dashes, form-feed characters |
| `normalize_whitespace()` | Collapses 3+ blank lines, trims trailing spaces |
| `expand_abbreviations()` | HRA → "house rent allowance HRA", TDS → "tax deducted at source TDS", etc. |
| `extract_key_fields()` | Regex extracts PAN, TAN, account number, employee ID, pay period |

Abbreviation expansion is critical for Indian documents that use only shorthand — without it, a payslip showing only "HRA 16,000" would miss the "house rent allowance" keyword.

### Step 3 — Classification (`src/classifier.py`)

Three passes per category — see [Section 7](#7-classification-logic-deep-dive) for full details. Highest score above `0.20` wins; otherwise labelled Others.

### Step 4 — Field Extraction (`src/preprocessor.py`)

| Field | Pattern example |
|---|---|
| PAN number | `ABCDE1234F` format |
| TAN number | `ABCD12345E` format |
| Account number | After "account no / number / #" label |
| Employee ID | After "emp(loyee) id / code" label |
| Pay period | Month name + year near "pay period" |

### Step 5 — Entity Extraction (`src/entity_extractor.py`)

Runs only in batch mode. Extracts category-specific entities for grouping and Excel report. See [Section 8](#8-entity-extraction-deep-dive).

### Step 6 — Grouping & Excel Report (`src/report_generator.py`)

- **Bank Statements** → grouped by normalised account number (fallback: holder name)
- **Payslips** → grouped by employee ID (fallback: employee name)
- **Tax Documents** → grouped by employee PAN (fallback: employee name)

---

## 6. Module Reference

### `extractor.py`

```python
extract_text_from_file(path: Path) -> tuple[str, str]
# Returns (extracted_text, method_name)
# method_name: "pdfplumber" | "pymupdf" | "claude_vision" | "plain_text"
```

### `preprocessor.py`

```python
preprocess(text: str, aggressive: bool = False) -> str
# Full cleaning pipeline. aggressive=True adds stemming + stopword removal (ML training only).

extract_key_fields(text: str) -> dict
# Returns: {"pan_number": "...", "account_number": "...", "employee_id": "...", ...}
```

### `classifier.py`

```python
RulesBasedClassifier().classify(text: str) -> ClassificationResult
MLClassifier().train(texts, labels)
MLClassifier().classify(text: str) -> ClassificationResult
EnsembleClassifier(rules_weight=0.4, ml_weight=0.6).classify(text) -> ClassificationResult
```

`ClassificationResult`:
```python
label: str          # "Bank Statement" | "Payslip" | "Tax Document" | "Others"
confidence: float   # 0.0 – 0.99
method: str         # "rules" | "ml" | "ensemble"
scores: dict        # raw score per category
reasoning: list     # why this label was chosen
```

### `entity_extractor.py`

```python
extract_entities(label: str, text: str, filename: str = "") -> dict
# Dispatcher → calls the correct extractor, returns {} for Others.

extract_bank_statement(text, filename) -> dict
# Keys: account_number, holder_name, bank_name, statement_month, filename

extract_payslip(text, filename) -> dict
# Keys: employee_id, employee_name, company, payslip_month, filename

extract_tax_document(text, filename) -> dict
# Keys: pan, employee_name, employer, assessment_year, filename
```

All functions return `""` for any field that cannot be found — they never raise exceptions.

### `report_generator.py`

```python
generate_report(pipeline_results: list, output_path: str = "document_summary.xlsx") -> str
# Returns absolute path of written Excel file.
```

### `pipeline.py`

```python
DocumentClassificationPipeline().run(file_path) -> PipelineResult
DocumentClassificationPipeline().run_batch(file_paths) -> list[PipelineResult]
```

`PipelineResult`:
```python
file_path, raw_text, cleaned_text, extraction_method
classification: ClassificationResult
extracted_fields: dict
processing_time_ms: float
error: Optional[str]   # None if successful
```

### `evaluator.py`

```python
evaluate(y_true: list, y_pred: list) -> dict
# Returns accuracy, macro_f1, per-class precision/recall/f1, confusion matrix

print_report(metrics: dict) -> None
```

---

## 7. Classification Logic Deep Dive

### The Scoring Engine

Every document is scored against each of the 3 active categories independently:

**Pass 1 — Keyword Matching**
```
Each keyword hit → +0.12  (capped at 0.65 from keywords alone)
```
Multi-word phrases use substring search. Single words use `\b` word-boundary regex to prevent `"da"` matching inside `"standard"` or `"Accidental"`.

**Pass 2 — Regex Pattern Matching**
```
Each pattern match → +0.18
```
Patterns detect structured data formats. For example:
```python
r"(opening|closing)\s*[:\-]\s*[\$₹£€]?[\d,]+\.\d{2}"
# Matches both "Opening: $2,465.44"  AND  "Opening Balance: ₹10,000.00"
```

**Pass 3 — Negative Keyword Penalty**
```
Each negative keyword hit → -0.20  (cumulative, not capped)
```
The penalty is **cumulative** — a salary certificate hitting 6 negative keywords gets `−1.20`, overriding a `+1.37` positive score. A flat penalty would fail in high-overlap documents.

**Threshold & Winner**

Highest score above `0.20` wins. If none clears the threshold → **Others**.

**Confidence Calculation**

Scores can be negative (from penalties), so they are shifted before normalising:
```python
min_score  = min(scores.values())
shifted    = {k: v - min_score for k, v in scores.items()}
confidence = shifted[best] / sum(shifted.values())   # always 0–99%
```

### Payslip Negative Keywords

The payslip category has the most extensive negative keyword list because many other HR document types share salary terminology:

```
# Salary letters
increment letter, salary increment, offer letter, appointment letter,
revised salary, revised ctc, effective from, dear ms, dear mr,
congratulations, with effect from

# NOC / Certificates
no objection certificate, noc, to whomsoever it may concern, to whomsoever,
this certifies, this is to certify, salary certificate, employment certificate,
experience certificate, relieving letter, permanent employee, date of joining

# PF Statements
pf statement, annual pf statement, epfo, employees provident fund organisation,
emp. contrib, empr. contrib, member name, uan
```

### Tax Document Negative Keywords

Insurance policies mention `PAN` and `Section 80C` as tax benefits but are not tax documents:
```
insurance, policy number, policy schedule, sum assured, annual premium,
premium term, life cover, death benefit, critical illness, policyholder, irdai
```

---

## 8. Entity Extraction Deep Dive

### Bank Statement

**Account Number** — handles all label variants:
```
"Account Number: 458912340921"  → 458912340921
"Account No.:    998877665544"  → 998877665544
"A/C Number:     334455667788"  → 334455667788
"Account: **** **** **** 6198"  → 6198 (masked)
```
Numbers are normalised (spaces/dashes removed) before grouping.

**Account Holder Name** — stops at the next label on the same line:
```
"Account Holder Name: Sneha Kulkarni Account Number: 112233445566"
→ "Sneha Kulkarni"   ✓  (not "Sneha Kulkarni Account Number")
```

### Payslip

**Employee ID** — matches all label variants:
```
"Employee ID: EMP1021"    → EMP1021
"Emp ID: EMP1045"         → EMP1045
"Employee Code: EMP1067"  → EMP1067
```

**Employee Name** — stops before the ID label, strips UAN and numbers:
```
"Employee Name: Rahul Sharma Employee ID: EMP1021"  → "Rahul Sharma"
"Employee Name: Arjun Mehta UAN 100456789067"       → "Arjun Mehta"
```

### Tax Document

**Employee PAN** (not Employer PAN) — 4-pass strategy:
1. Lines with `"PAN Number:"`, `"Employee PAN:"` — skipping any line with `"Employer"` or `"Deductor"`
2. Lines with `"Name of Employee"` that also contain a PAN pattern
3. Certification sentence: `"deducted from salary of Name (PAN: XXXXX)"`
4. Any PAN not on an employer line (fallback)

Handles OCR glitch `"Permanent Account NumbeCrMNPQ9012R"` (label merged with value) by scanning the entire label region for the PAN pattern.

### Name Cleaning (`_clean_name`)

All extracted names pass through cleaning:
```
"Sneha Kulkarni Account Number" → "Sneha Kulkarni"
"Rahul Sharma UAN 123456"       → "Rahul Sharma"
"Arjun Mehta Permanent"         → "Arjun Mehta"
```

---

## 9. Excel Report Format

`document_summary.xlsx` has four sheets:

**Sheet 1 — Summary**: total counts per category.

**Sheet 2 — Bank Statements**:
`Account Number | Account Holder | Bank Name | Latest Statement Month | Latest PDF File Name | Total Statements | All Months`

**Sheet 3 — Payslips**:
`Employee ID | Employee Name | Company | Latest Payslip Month | Latest PDF File Name | Total Payslips | All Months`

**Sheet 4 — Tax Documents**:
`PAN Number | Employee Name | Employer | Latest Assessment Year | File Name | Total Documents | All Assessment Years`

**Grouping fallback chain**: account number → holder name → UNKNOWN. Same pattern for payslips (employee ID → name) and tax docs (PAN → name).

Others documents appear only in the Summary count — excluded from all data sheets.

---

## 10. Web UI — `app.py`

```bash
python app.py   # then open http://localhost:5000
```

| Route | Method | Description |
|---|---|---|
| `GET /` | GET | DocSense drag-and-drop interface |
| `POST /classify` | POST | Accepts file, returns JSON |

```json
// Response
{
    "category":   "Bank Statement",
    "confidence": 0.92,
    "reason":     "Detected bank account transactions...",
    "filename":   "hdfc_march_2024.pdf"
}
```

**Security**: 20 MB max, allowed extensions only (`.pdf .jpg .jpeg .png .webp .bmp .tiff`), temp file deleted immediately after classification, fully stateless.

---

## 11. Batch CLI — `main.py`

Set at the top of `main.py`:
```python
INPUT_PATH   = r"new_outside_data"      # folder of PDFs (or single file)
VERBOSE      = False                     # True → show matched keywords
OUTPUT_JSON  = r"results.json"
OUTPUT_EXCEL = r"document_summary.xlsx"
```

```bash
python main.py
```

**Single file** → terminal result panel with label, confidence bar, scores.
**Folder** → live progress per file → summary table → `results.json` + `document_summary.xlsx` saved automatically.

---

## 12. Supported File Types

| Type | Extensions |
|---|---|
| Digital PDF | `.pdf` |
| Scanned PDF | `.pdf` (auto-detected when text < 50 chars) |
| Images | `.jpg` `.jpeg` `.png` `.bmp` `.tiff` `.webp` |
| Plain text | `.txt` |

---

## 13. Output Categories

| Label | Documents classified here |
|---|---|
| **Bank Statement** | HDFC, SBI, Axis, Kotak, ICICI, Wells Fargo, Citibank, PNC, Deutsche Bank, HSBC account statements |
| **Payslip** | Monthly salary slips with employee ID, earnings, deductions, net pay — Indian (HRA/DA/PF) and international |
| **Tax Document** | Form 16, Form 16A, Form 26AS, TDS certificates, ITR acknowledgements |
| **Others** | Insurance policies, loan statements, credit card statements, PF statements, salary certificates, NOCs, offer/increment/appointment letters, rental agreements, utility bills, and everything else |

---

## 14. Accuracy & Test Results

Tested on the **100-document dataset**:

| Category | Documents | Correctly Classified | Accuracy |
|---|---|---|---|
| Bank Statement | 33 | 33 | 100% |
| Payslip | 31 | 31 | 100% |
| Tax Document | 19 | 19 | 100% |
| Others | 17 | 17 | 100% |
| **Overall** | **100** | **100** | **100%** |

Entity extraction and grouping results:

| Category | Unique Groups Expected | Correctly Grouped |
|---|---|---|
| Bank Statements | 8 unique accounts | 8 / 8 ✓ |
| Payslips | 7 unique employees | 7 / 7 ✓ |
| Tax Documents | 9 unique PANs | 9 / 9 ✓ |

---

## 15. Known Issues Fixed

### Classification

| File / Type | Was Classified As | Root Cause | Fix |
|---|---|---|---|
| Insurance policy (HDFC Life) | Tax Document | Had `"Section 80C"` + PAN format | Added insurance keywords as tax_document negatives |
| Increment letter | Payslip | Had `"Basic Salary"` + `"house rent allowance"` from abbreviation expansion | Added letter-specific negatives; made penalty cumulative |
| PF statement | Payslip | Had `"provident fund"` keyword | Added `"epfo"`, `"annual pf statement"`, `"member name"`, `"uan"` as payslip negatives |
| NOC | Payslip | Had `"Employee ID"` field | Added `"no objection certificate"`, `"noc"`, `"to whomsoever"` as payslip negatives |
| Salary certificate | Payslip | Had all salary components — score 1.37 | Added `"this certifies"`, `"permanent employee"`, `"date of joining"` as payslip negatives |
| US bank statements | Others | Only Indian format keywords matched; US uses `"Opening: $x"` | Added US bank names, `"fdic"`, new regex for `Opening: $x.xx` |
| Flat penalty insufficient | — | Single `-0.35` regardless of number of negative hits | Changed to cumulative `-0.20 per hit` |

### Entity Extraction

| Issue | Root Cause | Fix |
|---|---|---|
| `"Sneha Kulkarni Account Number"` as holder name | Regex consumed rest of line | Lookahead stops at next label; `_clean_name()` strips trailing noise |
| Account number UNKNOWN | Only `Account Number:` matched; PDFs use `Account No.:` and `A/C Number:` too | Added all 3 variants to pattern |
| `"Rahul Sharma Employee ID: EMP1021"` as employee name | Name pattern consumed rest of line | Lookahead stops before ID/Code/UAN label |
| Employee ID not found | Only `Employee ID:` matched; PDFs use `Emp ID:` and `Employee Code:` | Added all 3 variants |
| `"da"` matching inside `"standard"` | Substring match instead of word-boundary | Applied `\b` regex for all single-word keywords |
| Employer PAN extracted instead of Employee PAN | Bare PAN scan picked first match | 4-pass strategy skipping lines with `"Employer"` / `"Deductor"` |
| OCR glitch `"Permanent Account NumbeCrMNPQ9012R"` | Label merged with value by OCR | Scan entire label region for PAN pattern |
| `"Arjun Mehta Permanent"` as name | `"Permanent"` leaked from next label | Added `"permanent account"` to `_NAME_NOISE` |
| Bank grouping: 4 groups instead of 8 | Account numbers with spaces not normalised before grouping | `_norm_account()` strips all spaces and dashes before using as dict key |

---

## 16. Adding New Categories

**Step 1 — Add to `CATEGORIES` in `classifier.py`:**
```python
"invoice": {
    "label": "Invoice",
    "keywords": [
        "invoice number", "bill to", "invoice date",
        "subtotal", "total amount due", "gst number",
    ],
    "patterns": [
        r"invoice\s*(no\.?|number|#)\s*[:\-]?\s*\w+",
        r"(subtotal|total\s+amount)\s*[:\-]?\s*[\$₹£€]?[\d,]+\.\d{2}",
    ],
    "negative_keywords": ["bank statement", "payslip", "form 16"],
    "weight": 1.0,
},
```

**Step 2 — Add to `REASON_TEMPLATES` in `classifier.py`.**

**Step 3 — Add an `extract_invoice()` function in `entity_extractor.py` and register it in `extract_entities()`.**

**Step 4 — Add grouping in `report_generator.py` and a new sheet in `generate_report()`.**

**Step 5 — Add to the `CAT` map in `templates/index.html`.**

Nothing else needs to change.

---

## 17. Dependencies

```
flask>=3.0.0        # Web server for browser UI
pdfplumber>=0.10.0  # Primary PDF text extraction
pymupdf>=1.23.0     # Fallback extraction + page rendering for scanned PDFs
Pillow>=10.0.0      # Image handling for Claude Vision upload
pandas>=2.0.0       # DataFrame building for Excel report
openpyxl>=3.1.0     # Excel file writing with styling

# Optional — ML classifier only
# scikit-learn>=1.4.0
# joblib>=1.3.0
```

No Tesseract, no spaCy, no transformers required.

---

## 18. Future Improvements

| Improvement | Benefit |
|---|---|
| LayoutLM / DocFormer transformer | Layout-aware classification, target ~99%+ accuracy |
| More output categories | Credit Card Statement, Loan Statement, Utility Bill, Invoice — rules engine makes this straightforward |
| Confidence threshold review queue | Flag < 60% confidence for human review |
| Active learning feedback loop | "Mark as Incorrect" in Web UI → periodic retraining |
| Multi-label classification | Some docs (Form 16 Part B) are both payslip + tax document |
| REST API with authentication | API key auth for integration with other systems |
| Database integration | PostgreSQL + audit trail + dashboard reporting |
| Multi-language support | Hindi, Tamil, regional Indian language keywords |

---

*DocSense — Content-driven document classification · No filename used · Built with Python, Flask, pdfplumber, and Claude Vision API*