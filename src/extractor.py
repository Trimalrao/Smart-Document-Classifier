"""
Text Extraction Module
- PDF files  : pdfplumber → PyMuPDF → Claude Vision (scanned PDF fallback)
- Image files: Claude Vision API  (no Tesseract required)
- Text files : plain read
"""

import base64
import io
import logging
import time
from pathlib import Path

logger = logging.getLogger(__name__)

PDF_EXTENSIONS   = {".pdf"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp", ".webp"}
TEXT_EXTENSIONS  = {".txt", ".csv", ".md", ".html", ".htm"}

# How many pages to send to Claude Vision for scanned PDFs (keep cost low)
MAX_SCANNED_PDF_PAGES = 3


# ─────────────────────────────────────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────────────────────────────────────

def extract_text_from_file(file_path) -> tuple[str, str]:
    """
    Auto-detect file type and extract text.
    Returns: (extracted_text, method_used)
    """
    path = Path(file_path)
    ext  = path.suffix.lower()

    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    if ext in PDF_EXTENSIONS:
        return extract_from_pdf(path)
    elif ext in IMAGE_EXTENSIONS:
        return extract_from_image(path)
    elif ext in TEXT_EXTENSIONS:
        return extract_from_text(path)
    else:
        raise ValueError(f"Unsupported file type: {ext}")


# ─────────────────────────────────────────────────────────────────────────────
# PDF
# ─────────────────────────────────────────────────────────────────────────────

def extract_from_pdf(path: Path) -> tuple[str, str]:
    """
    1. Try pdfplumber  (native digital PDF — best for tables)
    2. Try PyMuPDF     (fast fallback)
    3. If still sparse → scanned PDF → render pages → Claude Vision
    """
    text = _try_pdfplumber(path)

    if len(text.strip()) < 50:
        logger.info("pdfplumber sparse, trying PyMuPDF for %s", path.name)
        text = _try_pymupdf(path)

    if len(text.strip()) < 50:
        logger.info("PDF appears scanned, using Claude Vision for %s", path.name)
        text = _pdf_via_claude_vision(path)
        return text, "claude_vision_pdf"

    return text, "pdfplumber"


def _try_pdfplumber(path: Path) -> str:
    try:
        import pdfplumber
        pages = []
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text() or ""
                for table in page.extract_tables():
                    rows = [" | ".join(str(c) for c in row if c) for row in table if row]
                    page_text += "\n" + "\n".join(rows)
                pages.append(page_text)
        return "\n\n".join(pages)
    except ImportError:
        logger.warning("pdfplumber not installed — pip install pdfplumber")
        return ""
    except Exception as e:
        logger.warning("pdfplumber failed: %s", e)
        return ""


def _try_pymupdf(path: Path) -> str:
    try:
        import fitz
        doc   = fitz.open(str(path))
        pages = [page.get_text() for page in doc]
        doc.close()
        return "\n\n".join(pages)
    except ImportError:
        logger.warning("PyMuPDF not installed — pip install pymupdf")
        return ""
    except Exception as e:
        logger.warning("PyMuPDF failed: %s", e)
        return ""


def _pdf_via_claude_vision(path: Path) -> str:
    """Render PDF pages to PNG images and send to Claude Vision."""
    try:
        import fitz
    except ImportError:
        logger.error("PyMuPDF needed for scanned PDFs — pip install pymupdf")
        return ""

    try:
        doc    = fitz.open(str(path))
        texts  = []
        pages  = list(doc)[:MAX_SCANNED_PDF_PAGES]

        for i, page in enumerate(pages):
            mat = fitz.Matrix(2.0, 2.0)           # 2× resolution
            pix = page.get_pixmap(matrix=mat)
            png_bytes = pix.tobytes("png")
            b64 = base64.b64encode(png_bytes).decode()
            page_text = _call_claude_vision(b64, "image/png",
                                            f"page {i+1} of {path.name}")
            texts.append(page_text)

        doc.close()
        return "\n\n".join(texts)
    except Exception as e:
        logger.error("Claude Vision PDF fallback failed: %s", e)
        return ""


# ─────────────────────────────────────────────────────────────────────────────
# Image
# ─────────────────────────────────────────────────────────────────────────────

def extract_from_image(path: Path) -> tuple[str, str]:
    """
    Send the image directly to Claude Vision and extract all text.
    No Tesseract required.
    """
    ext_to_mime = {
        ".jpg":  "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png":  "image/png",
        ".bmp":  "image/png",   # convert to PNG first
        ".tiff": "image/png",
        ".tif":  "image/png",
        ".webp": "image/webp",
    }

    ext      = path.suffix.lower()
    raw      = path.read_bytes()
    mime     = ext_to_mime.get(ext, "image/jpeg")

    # Convert BMP/TIFF → PNG for better API compatibility
    if ext in {".bmp", ".tiff", ".tif"}:
        try:
            from PIL import Image as PILImage
            img = PILImage.open(io.BytesIO(raw)).convert("RGB")
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            raw  = buf.getvalue()
            mime = "image/png"
        except ImportError:
            pass  # send as-is if Pillow not available

    b64  = base64.b64encode(raw).decode()
    text = _call_claude_vision(b64, mime, path.name)
    return text, "claude_vision"


# ─────────────────────────────────────────────────────────────────────────────
# Claude Vision API call
# ─────────────────────────────────────────────────────────────────────────────

_VISION_PROMPT = """You are a document text extractor.
Extract ALL text visible in this document image exactly as it appears.
Include every word, number, label, table cell, header and footer.
Do NOT summarise or interpret — output only the raw extracted text.
Preserve the structure with newlines where natural."""


def _call_claude_vision(b64_data: str, mime_type: str, label: str = "") -> str:
    """
    Call the Anthropic API with the image and return extracted text.
    Uses the same API endpoint available in this environment.
    """
    try:
        import urllib.request
        import json

        payload = {
            "model": "claude-sonnet-4-20250514",
            "max_tokens": 2048,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": mime_type,
                                "data": b64_data,
                            },
                        },
                        {
                            "type": "text",
                            "text": _VISION_PROMPT,
                        },
                    ],
                }
            ],
        }

        data = json.dumps(payload).encode("utf-8")
        req  = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=data,
            headers={
                "Content-Type":      "application/json",
                "anthropic-version": "2023-06-01",
            },
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read().decode("utf-8"))

        # Extract text blocks
        text_parts = [
            block["text"]
            for block in result.get("content", [])
            if block.get("type") == "text"
        ]
        extracted = "\n".join(text_parts).strip()
        logger.info("Claude Vision extracted %d chars from %s", len(extracted), label)
        return extracted

    except Exception as e:
        logger.error("Claude Vision API call failed for %s: %s", label, e)
        return ""


# ─────────────────────────────────────────────────────────────────────────────
# Plain text
# ─────────────────────────────────────────────────────────────────────────────

def extract_from_text(path: Path) -> tuple[str, str]:
    for enc in ("utf-8", "latin-1", "cp1252"):
        try:
            return path.read_text(encoding=enc), "plain_text"
        except UnicodeDecodeError:
            continue
    raise ValueError(f"Could not decode {path}")