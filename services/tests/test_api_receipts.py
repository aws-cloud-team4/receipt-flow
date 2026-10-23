"""api-service: receipts — submit rules, warnings, access, delete, retake, meta."""

import boto3
from conftest import EMP, EMP2, REV
from helpers import new_receipt, sse_done
from ocr_worker.main import process
from receiptflow_common import store


def test_submit_requires_fields_and_finished_analysis(api):
    rid = new_receipt(api)
    assert api.post(f"/api/receipts/{rid}/submit", headers=EMP).json()["error"]["code"] == "analysis_pending"
    process(rid, f"incoming/{rid}.jpg")
    err = api.post(f"/api/receipts/{rid}/submit", headers=EMP).json()["error"]
    assert err["code"] == "missing_fields" and err["fields"] == ["purpose"]
    # The AI's category suggestion and the profile department are already filled.
    fields = api.get(f"/api/receipts/{rid}", headers=EMP).json()["fields"]
    assert fields["category"] == "food" and fields["department"] == "영업부"


def test_amount_mismatch_blocks_submit(api):
    rid = new_receipt(api)
    process(rid, f"incoming/{rid}.jpg")
    patch = {"total_amount": "14,000", "purpose": "a", "category": "기타"}
    receipt = api.patch(f"/api/receipts/{rid}", json={"fields": patch}, headers=EMP).json()
    assert [c["code"] for c in receipt["checks"]] == ["amount_mismatch"]
    assert api.post(f"/api/receipts/{rid}/submit", headers=EMP).json()["error"]["code"] == "check_failed"


def test_duplicate_warning(api):
    for _ in range(2):
        rid = new_receipt(api)
        process(rid, f"incoming/{rid}.jpg")
    receipt = api.get(f"/api/receipts/{rid}", headers=EMP).json()
    codes = [c["code"] for c in receipt["checks"]]
    assert "duplicate" in codes and "same_approval" in codes  # mock returns the same approval number
    assert receipt["fields"]["card_number"] == "4518-42**-****-1234"
    assert (
        receipt["fields"]["card_issuer"] == "신한카드" and receipt["fields"]["approval_number"] == "30012345"
    )


def test_access_control(api):
    rid = new_receipt(api)
    assert api.get(f"/api/receipts/{rid}", headers=EMP2).status_code == 403
    assert api.get(f"/api/receipts/{rid}", headers=REV).status_code == 200
    assert api.patch(f"/api/receipts/{rid}", json={"fields": {}}, headers=REV).status_code == 403
    assert api.get("/api/review/receipts", headers=EMP).status_code == 403
    assert api.get("/api/me").status_code == 401
    assert api.get("/api/receipts", headers=EMP2).json()["items"] == []


def test_delete_draft_removes_record_chat_and_images(api, chat):
    s3 = boto3.client("s3", region_name="ap-northeast-2")
    rid = new_receipt(api)
    s3.put_object(Bucket="rf-test-bucket", Key=f"raw/{rid}.jpg", Body=b"jpeg")
    process(rid, f"incoming/{rid}.jpg")
    sse_done(chat.post(f"/chat/receipts/{rid}/turn", json={"message": "팀 회의 다과"}, headers=EMP))

    assert api.delete(f"/api/receipts/{rid}", headers=EMP2).status_code == 403
    assert api.delete(f"/api/receipts/{rid}", headers=EMP).status_code == 204
    assert api.get(f"/api/receipts/{rid}", headers=EMP).status_code == 404
    assert store.list_messages(rid) == [] and store.list_events(rid) == []
    keys = [o["Key"] for o in s3.list_objects_v2(Bucket="rf-test-bucket").get("Contents", [])]
    assert f"raw/{rid}.jpg" not in keys and f"incoming/{rid}.jpg" not in keys
    assert process(rid, f"incoming/{rid}.jpg")  # a late queue message is dropped


def test_submitted_receipt_cannot_be_deleted(api):
    rid = new_receipt(api)
    process(rid, f"incoming/{rid}.jpg")
    api.patch(
        f"/api/receipts/{rid}",
        json={"fields": {"purpose": "팀 회의 다과", "category": "meeting"}},
        headers=EMP,
    )
    assert api.post(f"/api/receipts/{rid}/submit", headers=EMP).status_code == 200
    resp = api.delete(f"/api/receipts/{rid}", headers=EMP)
    assert resp.status_code == 409 and resp.json()["error"]["code"] == "not_deletable"


def test_category_saved_with_an_old_code_reads_as_the_new_one(api):
    rid = new_receipt(api)
    r = store.get_receipt(rid)
    store.update_receipt(rid, fields={**r["fields"], "category": "meal"})  # saved before the revision
    assert store.get_receipt(rid)["fields"]["category"] == "food"
    assert api.get(f"/api/receipts/{rid}", headers=EMP).json()["fields"]["category"] == "food"


def test_retake_starts_over(api, chat):
    rid = new_receipt(api)
    process(rid, f"incoming/{rid}.jpg")
    sse_done(chat.post(f"/chat/receipts/{rid}/turn", json={"event": "analysis_done"}, headers=EMP))
    sse_done(chat.post(f"/chat/receipts/{rid}/turn", json={"message": "맞아요"}, headers=EMP))
    api.patch(
        f"/api/receipts/{rid}", json={"fields": {"purpose": "팀 회의 다과", "category": "food"}}, headers=EMP
    )

    assert api.post(f"/api/receipts/{rid}/upload-url", headers=EMP).status_code == 200
    r = store.get_receipt(rid)
    assert (
        r["fields"]["purpose"] is None
        and r["fields"]["category"] is None
        and r["fields"]["merchant_name"] is None
    )
    assert r["fields"]["department"] == "영업부"  # profile value stays
    assert not r["result_confirmed_at"] and r["ai_filled"] == []
    assert chat.get(f"/chat/receipts/{rid}/messages", headers=EMP).json()["items"] == []
    assert store.list_events(rid)[-1]["action"] == "reuploaded"

    # the new reading is announced again (the old analysis_done event went with the chat)
    process(rid, f"incoming/{rid}.jpg")
    store.update_receipt(rid, analysis_status="done")
    first = sse_done(chat.post(f"/chat/receipts/{rid}/turn", json={"event": "analysis_done"}, headers=EMP))
    assert first["text"]


def test_meta_lists_departments(api):
    meta = api.get("/api/meta", headers=EMP).json()
    assert [d["name"] for d in meta["departments"]][:2] == ["경영지원부", "재무회계부"]
    assert len(meta["categories"]) == 10
