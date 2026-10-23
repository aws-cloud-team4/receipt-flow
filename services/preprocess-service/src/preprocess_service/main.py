"""Server-side receipt correction. The browser uploads the original to raw/{id}.jpg, then:

1. POST .../detect  → corners the server found (or a suggested frame) + blur score, for the user to check
2. POST .../apply   → crop with the corners the user confirmed, write incoming/{id}.jpg (starts analysis)

The original stays in raw/ so reviewers can compare it with the crop.
"""

import time
from typing import Any

from fastapi import Depends
from pydantic import BaseModel, Field
from receiptflow_common import aws, store
from receiptflow_common.auth import User, employee_only
from receiptflow_common.config import get_settings
from receiptflow_common.errors import ApiError, forbidden, not_found
from receiptflow_common.webapp import create_app

from .correct import BLUR_MIN, apply, detect

app = create_app("receipt-flow preprocess-service")

FRAME_MARGIN = 0.06  # suggested frame when no outline is found: 6% in from every edge


class ApplyBody(BaseModel):
    corners: list[list[float]] | None = Field(
        default=None, description="TL, TR, BR, BL in original pixels; null keeps the whole photo"
    )


def _owned(receipt_id: str, user: User) -> dict[str, Any]:
    receipt = store.get_receipt(receipt_id)
    if not receipt:
        raise not_found()
    if receipt["owner_sub"] != user.sub:
        raise forbidden()
    if receipt["review_status"] not in ("draft", "changes_requested"):
        raise ApiError(409, "not_editable", "제출된 증빙의 사진은 바꿀 수 없습니다.")
    return receipt


def _original(receipt_id: str) -> bytes:
    s3 = aws.client("s3")
    try:
        return s3.get_object(Bucket=get_settings().bucket, Key=f"raw/{receipt_id}.jpg")["Body"].read()
    except s3.exceptions.NoSuchKey as exc:
        raise ApiError(409, "not_uploaded", "원본 사진이 아직 업로드되지 않았습니다.") from exc


@app.post("/preprocess/receipts/{receipt_id}/detect")
def detect_corners(receipt_id: str, user: User = Depends(employee_only)) -> dict[str, Any]:
    _owned(receipt_id, user)
    started = time.perf_counter()
    try:
        found = detect(_original(receipt_id))
    except ValueError as exc:
        raise ApiError(422, "bad_image", str(exc)) from exc
    w, h, m = found.width, found.height, FRAME_MARGIN
    frame = [[w * m, h * m], [w * (1 - m), h * m], [w * (1 - m), h * (1 - m)], [w * m, h * (1 - m)]]
    return {
        "found": found.corners is not None,
        "corners": found.corners or frame,
        "width": w,
        "height": h,
        "blur_score": round(found.blur_score, 1),
        "blurry": found.blurry,
        "blur_min": BLUR_MIN,
        "elapsed_ms": int((time.perf_counter() - started) * 1000),
    }


@app.post("/preprocess/receipts/{receipt_id}/apply")
def apply_corners(receipt_id: str, body: ApplyBody, user: User = Depends(employee_only)) -> dict[str, Any]:
    _owned(receipt_id, user)
    original = _original(receipt_id)
    started = time.perf_counter()
    try:
        detected = detect(original).corners
        result = apply(original, body.corners)
    except ValueError as exc:
        raise ApiError(422, "bad_corners", str(exc)) from exc
    elapsed = int((time.perf_counter() - started) * 1000)
    # Writing incoming/ triggers the S3 → SQS → ocr-worker path.
    aws.client("s3").put_object(
        Bucket=get_settings().bucket,
        Key=f"incoming/{receipt_id}.jpg",
        Body=result.jpeg,
        ContentType="image/jpeg",
    )
    meta = {
        "where": "server",
        "corners": result.corners,
        "detected_corners": detected,
        "adjusted": result.corners is not None and result.corners != detected,
        "blur_score": round(result.blur_score, 1),
        "width": result.width,
        "height": result.height,
        "elapsed_ms": elapsed,
    }
    store.update_receipt(receipt_id, preprocess=meta)
    return meta
