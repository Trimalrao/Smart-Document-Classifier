#!/usr/bin/env python3
"""
DocSense — Batch CLI
════════════════════════════════════════════════════════════

HOW TO USE:
  1. Set INPUT_PATH below to a folder containing documents
  2. Run:  python main.py
  3. Results are saved to:
       • results.json          — raw classification output
       • document_summary.xlsx — grouped Excel report

════════════════════════════════════════════════════════════
"""

import json
import logging
import sys
import time
from pathlib import Path

logging.basicConfig(level=logging.CRITICAL)

# ════════════════════════════════════════════════════════════
#  ✏️  SET YOUR FOLDER PATH HERE
# ════════════════════════════════════════════════════════════

INPUT_PATH    = r"New_Group_dataset"    # folder containing PDFs

VERBOSE       = False
OUTPUT_JSON   = r"results.json"
OUTPUT_EXCEL  = r"document_summary.xlsx"

# ════════════════════════════════════════════════════════════
#  DO NOT EDIT BELOW THIS LINE
# ════════════════════════════════════════════════════════════

SUPPORTED = {".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp", ".txt"}

import os as _os
_COL = _os.name != "nt" or "WT_SESSION" in _os.environ
def _c(code, t): return f"\033[{code}m{t}\033[0m" if _COL else t
def G(t): return _c("92", t)
def R(t): return _c("91", t)
def Y(t): return _c("93", t)
def C(t): return _c("96", t)
def B(t): return _c("1",  t)
def D(t): return _c("2",  t)

LABEL_CLR = {
    "Bank Statement": lambda t: _c("94", t),
    "Payslip":        lambda t: _c("92", t),
    "Tax Document":   lambda t: _c("93", t),
    "Others":         lambda t: _c("90", t),
}
def cl(label): return LABEL_CLR.get(label, lambda t: t)(label)


def show_single(r):
    conf   = r.classification.confidence
    filled = int(conf * 20)
    bar    = G("█" * filled) + D("░" * (20 - filled))
    ok     = G("✓") if not r.error else R("✗")
    print()
    print(B("─" * 62))
    print(f"  {B('File      :')} {Path(r.file_path).name}")
    print(f"  {B('Status    :')} {ok}  {'Classified successfully' if not r.error else R(r.error)}")
    print(f"  {B('Label     :')} {cl(r.classification.label)}")
    print(f"  {B('Confidence:')} [{bar}] {C(f'{conf:.1%}')}")
    print(f"  {B('Method    :')} {r.classification.method}  |  "
          f"Extraction: {r.extraction_method}  |  "
          f"Time: {r.processing_time_ms:.0f} ms")
    if r.extracted_fields:
        print(f"  {B('Fields    :')} " +
              "  |  ".join(f"{k}: {C(v)}" for k, v in r.extracted_fields.items()))
    if VERBOSE and r.classification.reasoning:
        print(f"  {B('Reasoning :')}")
        for reason in r.classification.reasoning:
            print(f"      └─ {D(reason)}")
    print(B("─" * 62))
    print()


def show_batch(results, json_path, excel_path):
    from collections import Counter
    total  = len(results)
    errors = sum(1 for r in results if r.error)
    print()
    print(B("═" * 70))
    print(B(f"  BATCH RESULTS  —  {total} file(s)"))
    print(B("═" * 70))
    print(f"  {'#':<4} {'File':<34} {'Label':<25} {'Conf':>6}")
    print(f"  {'─'*4} {'─'*34} {'─'*25} {'─'*6}")
    for i, r in enumerate(results, 1):
        fname = Path(r.file_path).name
        fname = (fname[:31] + "...") if len(fname) > 34 else fname
        ok    = G("✓") if not r.error else R("✗")
        conf  = f"{r.classification.confidence:.0%}"
        print(f"  {ok} {i:<3} {fname:<34} {cl(r.classification.label):<25} {C(conf):>6}")
    print(B("─" * 70))
    print(f"  {B('Summary:')}")
    for label, cnt in Counter(r.classification.label for r in results).most_common():
        print(f"      {cl(label):<28}  {cnt} file(s)")
    if errors:
        print(f"  {R(f'  {errors} error(s) — see {json_path} for details.')}")
    print(B("═" * 70))
    print(f"\n  {G('✓')} results.json saved      →  {C(B(json_path))}")
    print(f"  {G('✓')} Excel report saved       →  {C(B(excel_path))}\n")


def main():
    path = Path(INPUT_PATH)
    if not path.exists():
        print(R(f"\n✗  Path not found: {INPUT_PATH}"))
        print(f"   Update INPUT_PATH in main.py and try again.\n")
        sys.exit(1)

    from src.pipeline import DocumentClassificationPipeline
    pipeline = DocumentClassificationPipeline()

    # ── Single file ───────────────────────────────────────────────────────────
    if path.is_file():
        if path.suffix.lower() not in SUPPORTED:
            print(R(f"\n✗  Unsupported file type: {path.suffix}"))
            sys.exit(1)
        print(D(f"\n  Classifying  {path.name} …"))
        result = pipeline.run(path)
        show_single(result)
        return

    # ── Folder (batch) ────────────────────────────────────────────────────────
    files = sorted(f for f in path.rglob("*") if f.suffix.lower() in SUPPORTED)
    if not files:
        print(Y(f"\n⚠  No supported documents found in: {INPUT_PATH}\n"))
        sys.exit(0)

    print(B(f"\n  Found {len(files)} document(s) in '{path.name}\\' — classifying …\n"))
    results = []
    t_start = time.perf_counter()

    for i, fp in enumerate(files, 1):
        print(f"  [{i:>3}/{len(files)}]  {fp.name:<44}", end=" ", flush=True)
        r = pipeline.run(fp)
        results.append(r)
        print(f"{G('✓') if not r.error else R('✗')}  {cl(r.classification.label)}")

    elapsed = time.perf_counter() - t_start

    # ── Save raw JSON ─────────────────────────────────────────────────────────
    Path(OUTPUT_JSON).write_text(
        json.dumps([r.to_dict() for r in results], indent=2, default=str),
        encoding="utf-8",
    )

    # ── Generate Excel report ─────────────────────────────────────────────────
    excel_out = OUTPUT_EXCEL
    try:
        from src.report_generator import generate_report
        print(f"\n  {D('Generating Excel report …')}", end=" ", flush=True)
        excel_out = generate_report(results, output_path=OUTPUT_EXCEL)
        print(G("✓"))
    except ImportError:
        print(R("✗"))
        print(R("  pandas / openpyxl not installed — skipping Excel report."))
        print(R("  Run:  pip install pandas openpyxl"))
    except Exception as e:
        print(R("✗"))
        print(R(f"  Excel report failed: {e}"))

    show_batch(results, OUTPUT_JSON, excel_out)
    print(D(f"  Total time: {elapsed:.1f}s  ({elapsed/len(files)*1000:.0f} ms/file avg)\n"))


if __name__ == "__main__":
    main()