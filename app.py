"""
DocSense — Document Classifier  (Flask backend)
Run:  python app.py
Open: http://localhost:5000
"""

import base64
import io
import logging
import os
import tempfile
from pathlib import Path

from flask import Flask, jsonify, render_template, request

logging.basicConfig(level=logging.WARNING)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024   # 20 MB limit

ALLOWED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff"}


# ── lazy-load pipeline so import errors surface clearly ────────────────────
_pipeline = None

def get_pipeline():
    global _pipeline
    if _pipeline is None:
        import sys
        sys.path.insert(0, str(Path(__file__).parent))
        from src.pipeline import DocumentClassificationPipeline
        _pipeline = DocumentClassificationPipeline()
    return _pipeline


# ── Routes ─────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/classify", methods=["POST"])
def classify():
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded."}), 400

    f = request.files["file"]
    if not f.filename:
        return jsonify({"error": "Empty filename."}), 400

    ext = Path(f.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        return jsonify({
            "error": f"Unsupported file type '{ext}'. "
                     f"Supported: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
        }), 400

    # Save to a temp file so the pipeline can read it normally
    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        f.save(tmp.name)
        tmp_path = tmp.name

    try:
        pipeline = get_pipeline()
        result   = pipeline.run(tmp_path)
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass

    if result.error:
        return jsonify({"error": f"Classification failed: {result.error}"}), 500

    # Build reason string
    from src.classifier import REASON_TEMPLATES
    reason = REASON_TEMPLATES.get(result.classification.label, "")
    if result.classification.reasoning:
        detail = result.classification.reasoning[0]
        reason = f"{reason} ({detail})"

    return jsonify({
        "category":   result.classification.label,
        "confidence": round(result.classification.confidence, 4),
        "reason":     reason,
        "filename":   f.filename,
        "method":     result.classification.method,
        "fields":     result.extracted_fields,
    })


if __name__ == "__main__":
    print("\n  DocSense Document Classifier")
    print("  ─────────────────────────────")
    print("  Open http://localhost:5000 in your browser\n")
    app.run(debug=True, port=5000)