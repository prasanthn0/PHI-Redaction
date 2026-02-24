"""Run the HIPAA de-identification pipeline against benchmark data and score.

Reads PDFs + ground-truth JSON produced by ``generate_benchmark.py``,
runs the pipeline, and reports precision / recall / F1 per PHI category
and overall.

Usage:
    python -m evaluation.run_benchmark [--data-dir evaluation/data]

Requires: the application dependencies (openai, pymupdf, etc.) and a
valid LLM provider configured via environment variables.
"""

import argparse
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

# Ensure src/ is importable when running from repo root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


def _load_manifest(data_dir: str):
    manifest_path = Path(data_dir) / "manifest.json"
    if not manifest_path.exists():
        print(f"No manifest.json in {data_dir}. Run generate_benchmark.py first.")
        sys.exit(1)
    with open(manifest_path) as f:
        return json.load(f)


def _normalize(text: str) -> str:
    """Lowercase, strip, collapse whitespace."""
    return " ".join(text.lower().split())


def _match_findings(ground_truth: list, detected: list):
    """Compare ground truth to detected findings.

    Returns (true_positives, false_positives, false_negatives) as lists.
    Matching is by normalised text + category.
    """
    gt_set = set()
    for item in ground_truth:
        key = (_normalize(item["text"]), item["category"])
        gt_set.add(key)

    det_set = set()
    for item in detected:
        cat = item.category if isinstance(item.category, str) else item.category.value
        key = (_normalize(item.text), cat)
        det_set.add(key)

    tp = gt_set & det_set
    fp = det_set - gt_set
    fn = gt_set - det_set
    return tp, fp, fn


def _compute_metrics(tp_count, fp_count, fn_count):
    precision = tp_count / (tp_count + fp_count) if (tp_count + fp_count) else 0.0
    recall = tp_count / (tp_count + fn_count) if (tp_count + fn_count) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return precision, recall, f1


def run_benchmark(data_dir: str, output_file: str = ""):
    """Run all benchmark PDFs and compute scores."""
    from api.config import get_settings
    from redaction.factory import build_pipeline

    manifest = _load_manifest(data_dir)
    data = Path(data_dir)
    settings = get_settings()

    pipeline = build_pipeline(
        provider=settings.llm_provider,
        openai_api_key=settings.openai_api_key,
        openai_model=settings.openai_model,
        openai_temperature=settings.openai_temperature,
        azure_endpoint=settings.azure_openai_endpoint,
        api_key=settings.azure_openai_api_key,
        deployment_name=settings.azure_openai_deployment_name,
        api_version=settings.azure_openai_api_version,
        enable_ocr=settings.ocr_enabled,
        deidentification_mode="placeholder",
    )

    # Accumulators
    total_tp, total_fp, total_fn = 0, 0, 0
    cat_tp = defaultdict(int)
    cat_fp = defaultdict(int)
    cat_fn = defaultdict(int)
    per_doc = []

    print(f"\nRunning benchmark on {len(manifest)} documents ...\n")
    print(f"{'Doc':>6}  {'PHI':>4}  {'Det':>4}  {'TP':>4}  {'FP':>4}  {'FN':>4}  {'Prec':>6}  {'Rec':>6}  {'F1':>6}  {'Time':>6}")
    print("-" * 72)

    for entry in manifest:
        pdf_path = str(data / entry["pdf"])
        gt_path = data / entry["ground_truth"]

        with open(gt_path) as f:
            gt_data = json.load(f)
        ground_truth = gt_data["phi_entities"]

        out_path = str(data / f"{Path(entry['pdf']).stem}_redacted.pdf")

        start = time.time()
        try:
            result = pipeline.process(input_path=pdf_path, output_path=out_path)
        except Exception as e:
            print(f"  {entry['pdf']}: FAILED - {e}")
            per_doc.append({"file": entry["pdf"], "error": str(e)})
            continue
        elapsed = time.time() - start

        tp, fp, fn = _match_findings(ground_truth, result.findings)
        p, r, f1 = _compute_metrics(len(tp), len(fp), len(fn))

        total_tp += len(tp)
        total_fp += len(fp)
        total_fn += len(fn)

        # Category-level accumulation
        for _, cat in tp:
            cat_tp[cat] += 1
        for _, cat in fp:
            cat_fp[cat] += 1
        for _, cat in fn:
            cat_fn[cat] += 1

        print(
            f"{entry['pdf']:>30}  {len(ground_truth):>4}  {len(result.findings):>4}  "
            f"{len(tp):>4}  {len(fp):>4}  {len(fn):>4}  "
            f"{p:>6.1%}  {r:>6.1%}  {f1:>6.1%}  {elapsed:>5.1f}s"
        )

        per_doc.append({
            "file": entry["pdf"],
            "ground_truth_count": len(ground_truth),
            "detected_count": len(result.findings),
            "tp": len(tp),
            "fp": len(fp),
            "fn": len(fn),
            "precision": round(p, 4),
            "recall": round(r, 4),
            "f1": round(f1, 4),
            "time_seconds": round(elapsed, 2),
        })

    # Overall
    print("-" * 72)
    o_p, o_r, o_f1 = _compute_metrics(total_tp, total_fp, total_fn)
    print(f"{'OVERALL':>30}  {'':>4}  {'':>4}  {total_tp:>4}  {total_fp:>4}  {total_fn:>4}  {o_p:>6.1%}  {o_r:>6.1%}  {o_f1:>6.1%}")

    # Per-category
    all_cats = sorted(set(list(cat_tp) + list(cat_fp) + list(cat_fn)))
    print(f"\nPer-category breakdown:\n")
    print(f"{'Category':<30}  {'TP':>4}  {'FP':>4}  {'FN':>4}  {'Prec':>6}  {'Rec':>6}  {'F1':>6}")
    print("-" * 72)
    for cat in all_cats:
        cp, cr, cf = _compute_metrics(cat_tp[cat], cat_fp[cat], cat_fn[cat])
        print(f"{cat:<30}  {cat_tp[cat]:>4}  {cat_fp[cat]:>4}  {cat_fn[cat]:>4}  {cp:>6.1%}  {cr:>6.1%}  {cf:>6.1%}")

    # Save results
    report = {
        "overall": {
            "tp": total_tp, "fp": total_fp, "fn": total_fn,
            "precision": round(o_p, 4), "recall": round(o_r, 4), "f1": round(o_f1, 4),
        },
        "per_category": {
            cat: {
                "tp": cat_tp[cat], "fp": cat_fp[cat], "fn": cat_fn[cat],
                "precision": round(_compute_metrics(cat_tp[cat], cat_fp[cat], cat_fn[cat])[0], 4),
                "recall": round(_compute_metrics(cat_tp[cat], cat_fp[cat], cat_fn[cat])[1], 4),
                "f1": round(_compute_metrics(cat_tp[cat], cat_fp[cat], cat_fn[cat])[2], 4),
            }
            for cat in all_cats
        },
        "per_document": per_doc,
    }

    out_file = output_file or str(data / "benchmark_results.json")
    with open(out_file, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\nDetailed results saved to {out_file}")


def main():
    parser = argparse.ArgumentParser(description="Run HIPAA benchmark evaluation")
    parser.add_argument("--data-dir", default="evaluation/data", help="Directory with benchmark PDFs")
    parser.add_argument("--output", default="", help="Output JSON file for results")
    args = parser.parse_args()
    run_benchmark(args.data_dir, args.output)


if __name__ == "__main__":
    main()

