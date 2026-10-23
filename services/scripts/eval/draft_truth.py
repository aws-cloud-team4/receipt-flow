"""Prepare real receipt photos and draft their ground truth with a strong model.

    1. Put photos (jpg/png/webp/heic) in services/scripts/eval/real/       (gitignored)
    2. uv run --with pillow --with pillow-heif python scripts/eval/draft_truth.py
    3. Open real/truth.csv in Excel, compare each row with its photo, fix values, put Y in `verified`
    4. uv run python scripts/eval/compare_models.py --set real

Photos are re-encoded to real/images/*.jpg (EXIF rotation applied, long side 1600px) so every model
sees the same bytes the app would upload. Re-running only drafts photos not yet in truth.csv.
"""

import argparse
import csv
import io
from pathlib import Path

from ocr_worker.extractor import NotAReceipt, extract
from PIL import Image, ImageOps

HERE = Path(__file__).parent
FIELDS = [
    "merchant_name",
    "business_number",
    "transaction_at",
    "supply_amount",
    "vat_amount",
    "total_amount",
    "payment_method",
    "card_issuer",
    "card_number",
    "approval_number",
]
COLUMNS = ["file", "verified", *FIELDS, "note"]
PHOTO_TYPES = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}


def prepare(src: Path, dst: Path, max_side: int = 1600) -> bytes:
    if src.suffix.lower() in {".heic", ".heif"}:
        from pillow_heif import register_heif_opener  # only needed for iPhone photos

        register_heif_opener()
    img = ImageOps.exif_transpose(Image.open(src)).convert("RGB")
    img.thumbnail((max_side, max_side))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=85)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(buf.getvalue())
    return buf.getvalue()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", default="real", help="folder under scripts/eval")
    ap.add_argument("--model", default="global.anthropic.claude-sonnet-5-5", help="model drafting truth")
    args = ap.parse_args()

    root = HERE / args.set
    truth_path = root / "truth.csv"
    rows: list[dict] = []
    if truth_path.exists():
        with truth_path.open(encoding="utf-8-sig", newline="") as f:
            rows = list(csv.DictReader(f))
    done = {r["file"] for r in rows}

    photos = sorted(p for p in root.iterdir() if p.is_file() and p.suffix.lower() in PHOTO_TYPES)
    for src in photos:
        rel = f"images/{src.stem}.jpg"
        if rel in done:
            continue
        image = prepare(src, root / rel)
        try:
            fields, *_ = extract(image, model=args.model)
            note = ""
        except NotAReceipt:
            fields, note = {}, "모델이 영수증이 아니라고 판단"
        except Exception as exc:
            fields, note = {}, f"초안 실패: {type(exc).__name__}"
        rows.append({"file": rel, "verified": "", **{k: fields.get(k) or "" for k in FIELDS}, "note": note})
        print(f"drafted {rel}")

    with truth_path.open("w", encoding="utf-8-sig", newline="") as f:  # utf-8-sig: Excel opens Korean fine
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    todo = sum(1 for r in rows if r["verified"].strip().upper() not in ("Y", "O"))
    print(f"{len(rows)} rows in {truth_path} - {todo} still need checking (set verified=Y)")


if __name__ == "__main__":
    main()
