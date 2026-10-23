"""Helpers shared by the test files (moto + mock AI)."""

import json

import boto3
from conftest import EMP


def sse_done(resp) -> dict:
    events = [block for block in resp.text.split("\n\n") if block.startswith("event: done")]
    return json.loads(events[-1].split("data: ", 1)[1])


def new_receipt(api, headers=EMP) -> str:
    resp = api.post("/api/receipts", headers=headers)
    assert resp.status_code == 201
    body = resp.json()
    assert "raw/" in body["upload"]["url"]  # the original; preprocess writes the crop to incoming/
    rid = body["receipt"]["id"]
    boto3.client("s3", region_name="ap-northeast-2").put_object(
        Bucket="rf-test-bucket", Key=f"incoming/{rid}.jpg", Body=b"jpeg"
    )
    assert api.post(f"/api/receipts/{rid}/uploaded", headers=headers).json()["analysis_status"] == "queued"
    return rid


def _photo() -> bytes:
    """A tilted white receipt on a dark desk, like a phone photo."""
    import cv2
    import numpy as np

    canvas = np.full((1200, 900, 3), 40, np.uint8)
    cv2.fillPoly(canvas, [np.array([[250, 150], [700, 220], [640, 1050], [190, 980]], np.int32)], (245,) * 3)
    return cv2.imencode(".jpg", canvas)[1].tobytes()
