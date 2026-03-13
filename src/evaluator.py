"""
Evaluation Module
Computes classification metrics and generates reports.
"""

from collections import defaultdict
import json


def evaluate(y_true: list[str], y_pred: list[str]) -> dict:
    """
    Compute per-class and macro metrics.

    Returns:
        {
          "accuracy": float,
          "per_class": {label: {"precision", "recall", "f1", "support"}},
          "macro_f1": float,
          "confusion_matrix": {true: {pred: count}}
        }
    """
    assert len(y_true) == len(y_pred), "Lengths must match"

    labels = sorted(set(y_true) | set(y_pred))
    tp = defaultdict(int)
    fp = defaultdict(int)
    fn = defaultdict(int)
    confusion = defaultdict(lambda: defaultdict(int))

    for t, p in zip(y_true, y_pred):
        confusion[t][p] += 1
        if t == p:
            tp[t] += 1
        else:
            fp[p] += 1
            fn[t] += 1

    per_class = {}
    for label in labels:
        prec = tp[label] / (tp[label] + fp[label]) if (tp[label] + fp[label]) else 0.0
        rec = tp[label] / (tp[label] + fn[label]) if (tp[label] + fn[label]) else 0.0
        f1 = (2 * prec * rec / (prec + rec)) if (prec + rec) else 0.0
        support = sum(1 for t in y_true if t == label)
        per_class[label] = {
            "precision": round(prec, 4),
            "recall": round(rec, 4),
            "f1": round(f1, 4),
            "support": support,
        }

    accuracy = sum(t == p for t, p in zip(y_true, y_pred)) / len(y_true)
    macro_f1 = sum(v["f1"] for v in per_class.values()) / len(per_class)

    return {
        "accuracy": round(accuracy, 4),
        "macro_f1": round(macro_f1, 4),
        "per_class": per_class,
        "confusion_matrix": {k: dict(v) for k, v in confusion.items()},
    }


def print_report(metrics: dict) -> None:
    """Pretty-print evaluation report."""
    print("\n" + "=" * 60)
    print("CLASSIFICATION EVALUATION REPORT")
    print("=" * 60)
    print(f"Overall Accuracy : {metrics['accuracy']:.2%}")
    print(f"Macro F1         : {metrics['macro_f1']:.4f}")
    print()

    header = f"{'Class':<22} {'Precision':>10} {'Recall':>8} {'F1':>8} {'Support':>9}"
    print(header)
    print("-" * 60)
    for label, m in metrics["per_class"].items():
        print(
            f"{label:<22} {m['precision']:>10.4f} {m['recall']:>8.4f} "
            f"{m['f1']:>8.4f} {m['support']:>9}"
        )

    print("\nConfusion Matrix (rows=actual, cols=predicted):")
    all_labels = sorted(metrics["per_class"].keys())
    col_w = max(len(l) for l in all_labels) + 2
    print(" " * col_w + "".join(f"{l:>{col_w}}" for l in all_labels))
    for true_label in all_labels:
        row = metrics["confusion_matrix"].get(true_label, {})
        counts = "".join(f"{row.get(p, 0):>{col_w}}" for p in all_labels)
        print(f"{true_label:<{col_w}}{counts}")
    print("=" * 60)
