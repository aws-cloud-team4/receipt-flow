"""preprocess-service: server crop with the person's corner adjustment."""

import boto3
from conftest import EMP, EMP2
from helpers import _photo


def test_server_crop_with_user_adjustment(api, pre):
    rid = api.post("/api/receipts", headers=EMP).json()["receipt"]["id"]
    s3 = boto3.client("s3", region_name="ap-northeast-2")
    assert (
        pre.post(f"/preprocess/receipts/{rid}/detect", headers=EMP).json()["error"]["code"] == "not_uploaded"
    )
    s3.put_object(Bucket="rf-test-bucket", Key=f"raw/{rid}.jpg", Body=_photo())

    # Unconfirmed photos are not listed yet.
    assert api.get("/api/receipts", headers=EMP).json()["items"] == []

    found = pre.post(f"/preprocess/receipts/{rid}/detect", headers=EMP).json()
    assert found["found"] is True and found["blurry"] is False
    assert (found["width"], found["height"]) == (900, 1200)
    tl = found["corners"][0]
    assert abs(tl[0] - 250) < 15 and abs(tl[1] - 150) < 15
    assert pre.post(f"/preprocess/receipts/{rid}/detect", headers=EMP2).status_code == 403

    bad = pre.post(
        f"/preprocess/receipts/{rid}/apply", json={"corners": [[0, 0], [5, 0], [5, 5], [0, 5]]}, headers=EMP
    )
    assert bad.json()["error"]["code"] == "bad_corners"

    adjusted = [[240, 140], *found["corners"][1:]]
    meta = pre.post(f"/preprocess/receipts/{rid}/apply", json={"corners": adjusted}, headers=EMP).json()
    assert meta["where"] == "server" and meta["adjusted"] is True and meta["height"] > meta["width"]
    assert s3.head_object(Bucket="rf-test-bucket", Key=f"incoming/{rid}.jpg")["ContentLength"] > 0

    receipt = api.post(f"/api/receipts/{rid}/uploaded", headers=EMP).json()
    assert receipt["analysis_status"] == "queued" and receipt["preprocess"]["corners"][0] == [240.0, 140.0]
    detail = api.get(f"/api/receipts/{rid}", headers=EMP).json()
    assert f"incoming/{rid}.jpg" in detail["image_url"] and f"raw/{rid}.jpg" in detail["original_url"]
    assert [r["id"] for r in api.get("/api/receipts", headers=EMP).json()["items"]] == [rid]

    # Keeping the whole photo is allowed (no outline found and the user did not draw one).
    whole = pre.post(f"/preprocess/receipts/{rid}/apply", json={"corners": None}, headers=EMP).json()
    assert whole["corners"] is None and (whole["width"], whole["height"]) == (900, 1200)

    # A new photo clears the old crop result.
    receipt = api.post(f"/api/receipts/{rid}/upload-url", headers=EMP).json()["receipt"]
    assert receipt["preprocess"] is None and receipt["analysis_status"] == "waiting"
