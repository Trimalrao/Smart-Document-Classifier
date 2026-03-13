# Document Content Classifier

Automatically classifies documents (PDFs, scanned images, text files) into:

| Category | Examples |
|---|---|
| **Bank Statement** | Account statements, passbooks |
| **Payslip** | Salary slips, pay stubs |
| **Tax Document** | Form 16, Form 26AS, ITR |
| **Others** | Invoices, contracts, misc. |

---

## Project Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                  INPUT DOCUMENTS                             │
│         PDF  │  Scanned Image  │  Plain Text                 │
└──────┬────────────────┬─────────────────┬────────────────────┘
       │                │                 │
       ▼                ▼                 ▼
┌─────────────────────────────────────────────────────────────┐
│                   EXTRACTOR (extractor.py)                  │
│  pdfplumber → PyMuPDF → OCR fallback   │  Tesseract OCR    │
│  (native PDF)            (scanned PDF) │  (image files)    │
└─────────────────────────────┬───────────────────────────────┘
                              │  raw text
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                PREPROCESSOR (preprocessor.py)               │
│  Unicode normalise → OCR artifact fix → whitespace norm     │
│  → abbreviation expansion → (optional: stopword removal)   │
└─────────────────────────────┬───────────────────────────────┘
                              │  cleaned text
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                  CLASSIFIER (classifier.py)                 │
│                                                             │
│   ┌─────────────────┐    ┌─────────────────┐               │
│   │  Rules-Based    │    │  ML Classifier  │               │
│   │  (keywords +    │    │  TF-IDF + LR    │               │
│   │   regex)        │    │  (sklearn)      │               │
│   └────────┬────────┘    └────────┬────────┘               │
│            └──────────┬───────────┘                         │
│                       ▼                                     │
│              EnsembleClassifier                             │
│           (weighted score fusion)                           │
└─────────────────────────────┬───────────────────────────────┘
                              │  label + confidence + scores
                              ▼
┌─────────────────────────────────────────────────────────────┐
│             FIELD EXTRACTOR (preprocessor.py)               │
│   PAN  │  TAN  │  Account No  │  Employee ID  │  Period     │
└─────────────────────────────┬───────────────────────────────┘
                              │
                              ▼
                    PipelineResult (JSON)
```

---

## Quick Start

### 1. Install dependencies

```bash
# Python packages
pip install -r requirements.txt

# Tesseract OCR engine (required for scanned images)
# Ubuntu:  sudo apt install tesseract-ocr tesseract-ocr-eng
# macOS:   brew install tesseract
# Windows: https://github.com/UB-Mannheim/tesseract/wiki
```

### 2. Classify a single document

```bash
python main.py classify path/to/document.pdf
```

### 3. Classify a whole folder

```bash
python main.py classify path/to/folder/ --output results.json
```

### 4. Verbose output (with reasoning)

```bash
python main.py classify document.pdf --verbose
```

---

## Python API

```python
from src.pipeline import DocumentClassificationPipeline

pipeline = DocumentClassificationPipeline()
result = pipeline.run("salary_jan2024.pdf")

print(result.classification.label)       # "Payslip"
print(result.classification.confidence)  # 0.87
print(result.extracted_fields)           # {"employee_id": "EMP00123", ...}
```

---

## Document Processing Workflow

```
New Document arrives
        │
        ▼
  Detect file type
  ┌─────┴──────┐
  │            │
 PDF        Image/Scan
  │            │
  ▼            ▼
Has native   Tesseract
text? ──No──► OCR
  │
  Yes
  │
  ▼
pdfplumber
(text + tables)
  │
  ▼
Text < 50 chars?
  │ Yes → PyMuPDF → Still sparse? → OCR
  │ No
  ▼
Preprocess text
  │
  ▼
Score against each category
  │   bank_statement: 0.72
  │   payslip:        0.18
  │   tax_document:   0.05
  │
  ▼
Best score > 0.15?
  │ No  → label = "Others"
  │ Yes → label = top category
  ▼
Extract key fields (PAN, account no, ...)
  │
  ▼
Return PipelineResult
```

---

## Tools & Libraries Reference

| Task | Library | Notes |
|---|---|---|
| Native PDF extraction | `pdfplumber` | Best for tables and structured PDFs |
| PDF fallback / rendering | `pymupdf` (fitz) | Fast, also handles scanned PDFs |
| OCR engine | `pytesseract` + `Tesseract` | Open-source, supports 100+ languages |
| Image preprocessing | `Pillow` | Grayscale, contrast, sharpening |
| ML classification | `scikit-learn` | TF-IDF + Logistic Regression |
| Model persistence | `joblib` | Save/load sklearn pipelines |
| Transformer (future) | `transformers` + HuggingFace | BERT/LayoutLM for higher accuracy |

---

## Training the ML Classifier

Prepare a JSON file `data/training_samples.json`:

```json
[
  {"text": "Account No 123456 IFSC SBIN0001 debit credit balance ...", "label": "Bank Statement"},
  {"text": "Employee ID EMP001 Basic Pay HRA PF Gross Net Salary ...", "label": "Payslip"},
  {"text": "Form 16 TAN PAN Assessment Year 2023-24 Section 80C ...", "label": "Tax Document"},
  {"text": "Invoice GST 18 percent payment due 30 days ...",           "label": "Others"}
]
```

Train and save:

```bash
python main.py train --data data/training_samples.json --save models/ml_model.pkl
```

Classify using the trained model:

```bash
python main.py classify document.pdf --model models/ml_model.pkl
```

---

## Adding New Categories

1. Open `src/classifier.py`
2. Add an entry to the `CATEGORIES` dict:

```python
CATEGORIES["invoice"] = {
    "label": "Invoice",
    "keywords": [
        "invoice", "bill to", "gst number", "hsn code",
        "taxable value", "cgst", "sgst", "igst",
    ],
    "patterns": [
        r"invoice\s*(no|number|#)\s*[:\-]?\s*\w+",
        r"(cgst|sgst|igst)\s*@?\s*\d+%",
        r"gst(in)?\s*[:\-]?\s*\d{2}[A-Z]{5}\d{4}[A-Z]{1,3}",
    ],
    "negative_keywords": ["payslip", "bank statement", "form 16"],
    "weight": 1.0,
}
```

No other changes needed — the classifier auto-discovers all categories.

---

## Evaluation

Prepare ground truth and prediction lists:

```bash
python main.py evaluate \
  --labels data/true_labels.json \
  --predictions data/pred_labels.json
```

Example output:

```
============================================================
CLASSIFICATION EVALUATION REPORT
============================================================
Overall Accuracy : 91.20%
Macro F1         : 0.9087

Class                  Precision   Recall       F1   Support
------------------------------------------------------------
Bank Statement            0.9400   0.9200   0.9299       100
Payslip                   0.9300   0.9500   0.9399        80
Tax Document              0.8900   0.8800   0.8850        60
Others                    0.8700   0.8600   0.8650        40
============================================================
```

### Recommended Metrics

| Metric | Why it matters |
|---|---|
| **Accuracy** | Overall correctness |
| **Precision (per class)** | When we label X, how often correct? |
| **Recall (per class)** | Of all real X docs, how many caught? |
| **F1 Score** | Harmonic mean — useful when classes are imbalanced |
| **Macro F1** | Average F1 across all classes (treats all equally) |
| **Confusion Matrix** | Shows exactly which categories get confused |

---

## Tips for Ambiguous Documents & Improving Accuracy

### Handling Ambiguous Documents

1. **Use confidence thresholds** — If `confidence < 0.5`, flag for human review instead of blindly accepting.
2. **Check extracted fields** — A document labelled as a Payslip but with no `employee_id` extracted is suspicious.
3. **Ensemble voting** — The `EnsembleClassifier` combines rules + ML scores. With more ML training data, ML weight can be increased from 0.6 → 0.8.
4. **Log low-confidence predictions** — Build a feedback loop where reviewers correct mistakes, creating new training samples.

### Improving Accuracy Over Time

| Strategy | Description |
|---|---|
| **Active learning** | Prioritise uncertain documents for human labelling |
| **Domain keywords** | Add company-specific terms (e.g. your bank's header text) to keyword lists |
| **More training data** | 50+ samples per class is a good minimum; 200+ is better |
| **LayoutLM / DocFormer** | Transformer models that understand document layout — much higher accuracy for complex/mixed documents |
| **Language support** | Add `lang="hin+eng"` to Tesseract for Hindi documents |
| **Multi-label** | Some documents may be both a payslip and a tax document (Form 16 Part B) — extend `ClassificationResult` to support multiple labels |

---

## Project Structure

```
doc_classifier/
├── main.py                  # CLI entry point
├── requirements.txt
├── src/
│   ├── __init__.py
│   ├── extractor.py         # PDF / OCR / text extraction
│   ├── preprocessor.py      # Text cleaning + field extraction
│   ├── classifier.py        # Rules + ML + Ensemble classifiers
│   ├── pipeline.py          # End-to-end orchestration
│   └── evaluator.py         # Metrics and reporting
├── tests/
│   └── test_classifier.py   # Unit tests
├── data/                    # Training samples, labels (gitignore raw docs)
└── models/                  # Saved ML model files
```
