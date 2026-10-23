"""Run the server's outline detection on a folder of photos and save side-by-side previews.

    uv run python scripts/eval/check_crop.py ../영수증            # writes ../영수증/_crop/

Each preview shows the original with the detected outline (green, or a red default frame when
nothing was found) next to the crop the AI would read. Prints found / blur per photo.
"""

import sys
from pathlib import Path

import cv2
import numpy as np
from preprocess_service.correct import BLUR_MIN, apply, detect

PHOTO_TYPES = {".jpg", ".jpeg", ".png", ".webp"}
PREVIEW_HEIGHT = 900


def prepare(path: Path) -> bytes:
    """Same as the browser: EXIF rotation, long side 2400px, JPEG 90."""
    from PIL import Image, ImageOps

    img = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    img.thumbnail((2400, 2400))
    bgr = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
    _, buf = cv2.imencode(".jpg", bgr, [cv2.IMWRITE_JPEG_QUALITY, 90])
    return buf.tobytes()


def fit(img: np.ndarray) -> np.ndarray:
    f = PREVIEW_HEIGHT / img.shape[0]
    return cv2.resize(img, (int(img.shape[1] * f), PREVIEW_HEIGHT))


def main() -> None:
    folder = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    out = folder / "_crop"
    out.mkdir(exist_ok=True)
    photos = sorted(p for p in folder.iterdir() if p.suffix.lower() in PHOTO_TYPES)
    found_count = 0
    for i, path in enumerate(photos, 1):
        data = prepare(path)
        d = detect(data)
        original = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
        if d.corners:
            found_count += 1
            quad = np.array(d.corners, np.int32)
            color = (60, 200, 60)
        else:
            w, h, m = d.width, d.height, 0.06
            quad = np.array(
                [[w * m, h * m], [w * (1 - m), h * m], [w * (1 - m), h * (1 - m)], [w * m, h * (1 - m)]],
                np.int32,
            )
            color = (40, 40, 230)
        cv2.polylines(original, [quad], True, color, max(4, d.width // 200))
        crop = cv2.imdecode(np.frombuffer(apply(data, d.corners).jpeg, np.uint8), cv2.IMREAD_COLOR)
        cv2.imwrite(str(out / f"{i:02d}.jpg"), np.hstack([fit(original), fit(crop)]))
        status = "found" if d.corners else "NOT FOUND"
        blur = f"blur {d.blur_score:.0f}" + (" BLURRY" if d.blur_score < BLUR_MIN else "")
        print(f"{i:02d}  {status:9}  {blur}")
    print(f"{found_count}/{len(photos)} outlines found; previews in {out}")


if __name__ == "__main__":
    main()
