"""Run the real extractor over an eval set with several Bedrock models and score field accuracy.

    uv run python scripts/eval/compare_models.py                       # synthetic set, default models
    uv run python scripts/eval/compare_models.py --set real            # your real receipts (verified rows)
    uv run python scripts/eval/compare_models.py global.anthropic.claude-sonnet-5-5

Costs real Bedrock tokens (about 3k input tokens per image per model). Writes results.json next to
this file. Prices are approximate per-million-token list prices used only to rank cost.
"""

import argparse
import csv
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from ocr_worker.extractor import NotAReceipt, extract

HERE = Path(__file__).parent
FIELDS = [
    "merchant_name",
    "business_number",
    "transaction_at",
    "supply_amount",
    "vat_amount",
    "exempt_amount",
    "total_amount",
    "payment_method",
    "card_issuer",
    "card_number",
    "approval_number",
]
CORE = ["merchant_name", "transaction_at", "total_amount"]

MODELS = {  # id: (label, $ per 1M input, $ per 1M output)
    "global.anthropic.claude-haiku-4-5-20251001-v1:0": ("Haiku 4.5", 1.0, 5.0),
    "global.anthropic.claude-haiku-5-5": ("Haiku 5.5", 0.10, 0.50),
    "global.anthropic.claude-sonnet-4-6": ("Sonnet 4.6", 3.0, 15.0),
    "global.anthropic.claude-sonnet-5": ("Sonnet 5", 2.0, 10.0),
    "global.anthropic.claude-sonnet-5-5": ("Sonnet 5.5", 2.0, 10.0),
}


def norm(key: str, value, truth=None):
    if value in (None, ""):
        return None
    if key == "merchant_name":  # (주)/㈜/주식회사 are the same company; spacing does not count
        return re.sub(r"\(주\)|㈜|주\)|주식회사|[\s()]", "", str(value))
    if key == "card_number":  # as printed; spacing, hyphens and how many * a run has do not count
        return re.sub(r"\*+", "*", re.sub(r"[\s-]", "", str(value)))
    if key == "card_issuer":
        return re.sub(r"[\s-]", "", str(value))
    if key == "approval_number":  # a "(0)" after the number is a slip code, not part of it
        return re.sub(r"\D", "", re.sub(r"\(\d\)$", "", str(value).strip()))
    if key == "business_number":
        return re.sub(r"\D", "", str(value))
    if key == "transaction_at":
        text = str(value).replace(" ", "T")
        # A truth with only a date is compared on the date part.
        return text[:10] if truth is not None and len(str(truth)) <= 10 else text[:16]
    if key in ("supply_amount", "vat_amount", "exempt_amount", "total_amount"):
        return int(re.sub(r"[^\d-]", "", str(value)) or 0)
    return str(value).strip()


def load_truth(root: Path) -> dict[str, dict]:
    """truth.json (synthetic) or truth.csv (real, only rows marked verified=Y)."""
    if (root / "truth.json").exists():
        return json.loads((root / "truth.json").read_text(encoding="utf-8"))
    with (root / "truth.csv").open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    verified = [r for r in rows if r.get("verified", "").strip().upper() in ("Y", "O")]
    if len(verified) < len(rows):
        print(f"using {len(verified)} verified of {len(rows)} rows in truth.csv")

    # Only the columns the file has are compared ("null" or empty = not printed).
    def value(v):
        return None if v is None or v.strip().lower() in ("", "null") else v.strip()

    return {r["file"]: {k: value(r[k]) for k in FIELDS if k in r} for r in verified}


def run_one(root: Path, model: str, name: str, truth: dict) -> dict:
    image = (root / name).read_bytes()
    try:
        fields, needs_check, usage, _ = extract(image, model=model)
    except NotAReceipt:
        fields, needs_check, usage = {}, [], {"input_tokens": 0, "output_tokens": 0, "latency_ms": 0}
    except Exception as exc:  # report per-case failures instead of aborting the run
        return {"name": name, "error": f"{type(exc).__name__}: {exc}"[:300]}
    wrong = [k for k in FIELDS if k in truth and norm(k, fields.get(k), truth[k]) != norm(k, truth[k])]
    return {
        "name": name,
        "wrong": wrong,
        "got": {k: fields.get(k) for k in wrong},
        "want": {k: truth[k] for k in wrong},
        "compared": [k for k in FIELDS if k in truth],
        "flagged": needs_check,
        "usage": usage,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("models", nargs="*", help="Bedrock model ids (default: all in MODELS)")
    ap.add_argument("--set", default="set", help="folder under scripts/eval (set = synthetic, real = yours)")
    args = ap.parse_args()
    root = HERE / args.set
    truth = load_truth(root)
    if not truth:
        raise SystemExit(f"no verified receipts in {root}")
    models = args.models or list(MODELS)
    results = {}
    for model in models:
        label, pin, pout = MODELS.get(model, (model, 0, 0))
        started = time.time()
        with ThreadPoolExecutor(max_workers=4) as pool:
            rows = list(pool.map(lambda n, m=model: run_one(root, m, n, truth[n]), truth))
        ok = [r for r in rows if "error" not in r]
        n_fields = sum(len(r["compared"]) for r in ok)
        field_acc = 1 - sum(len(r["wrong"]) for r in ok) / n_fields if ok else 0
        core_acc = sum(all(k not in r["wrong"] for k in CORE) for r in ok) / len(rows)
        tin = sum(r["usage"]["input_tokens"] for r in ok)
        tout = sum(r["usage"]["output_tokens"] for r in ok)
        lat = sorted(r["usage"]["latency_ms"] for r in ok)
        summary = {
            "label": label,
            "receipts": len(rows),
            "errors": len(rows) - len(ok),
            "core_all_correct": round(core_acc, 3),
            "field_accuracy": round(field_acc, 3),
            "median_latency_s": round(lat[len(lat) // 2] / 1000, 1) if lat else None,
            "cost_per_receipt_usd": round((tin * pin + tout * pout) / 1e6 / max(len(ok), 1), 5),
            "wall_s": round(time.time() - started, 1),
        }
        results[model] = {"summary": summary, "rows": rows}
        print(json.dumps(summary, ensure_ascii=False))
        per_field = {}
        for k in FIELDS:
            seen = [r for r in ok if k in r["compared"]]
            per_field[k] = f"{sum(k not in r['wrong'] for r in seen)}/{len(seen)}"
        print("  fields:", json.dumps(per_field, ensure_ascii=False))
        for r in rows:
            if r.get("error") or r["wrong"]:
                print("  ", r["name"], r.get("error") or {k: [r["got"][k], r["want"][k]] for k in r["wrong"]})
    (root / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
