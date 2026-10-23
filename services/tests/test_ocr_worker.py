"""ocr-worker: queue events, extraction results and what a person typed."""

import json

import boto3
from conftest import EMP
from helpers import new_receipt, sse_done
from ocr_worker.main import poll_once, process, receipt_ids


def test_worker_reads_s3_event_from_queue(api):
    rid = new_receipt(api)
    event = {"Records": [{"s3": {"object": {"key": f"incoming/{rid}.jpg"}}}]}
    sqs = boto3.client("sqs", region_name="ap-northeast-2")
    url = sqs.get_queue_url(QueueName="rf-test")["QueueUrl"]
    sqs.send_message(QueueUrl=url, MessageBody=json.dumps(event))
    assert poll_once(wait=0) == 1
    assert api.get(f"/api/receipts/{rid}", headers=EMP).json()["analysis_status"] == "done"
    assert receipt_ids({"Event": "s3:TestEvent"}) == []


def test_seeded_test_data_is_never_sent_to_the_model(api, monkeypatch):
    from receiptflow_common import store

    rid = new_receipt(api)
    store.update_receipt(rid, seed="dev", analysis_status="done", result_confirmed_at="2026-10-01T10:00:00")

    def no_model(_):
        raise AssertionError("seeded receipts must not reach the model")

    monkeypatch.setattr("ocr_worker.main.extract", no_model)
    assert process(rid, f"incoming/{rid}.jpg") is True  # the message is dropped
    after = store.get_receipt(rid)
    assert after["analysis_status"] == "done" and after["result_confirmed_at"] == "2026-10-01T10:00:00"


def test_employee_typed_values_win_over_late_extraction(api):
    rid = new_receipt(api)
    api.patch(f"/api/receipts/{rid}", json={"fields": {"merchant_name": "직접 입력"}}, headers=EMP)
    process(rid, f"incoming/{rid}.jpg")
    fields = api.get(f"/api/receipts/{rid}", headers=EMP).json()["fields"]
    assert fields["merchant_name"] == "직접 입력" and fields["total_amount"] == 13500


def test_ai_filled_marks_model_values_until_a_person_edits(api, chat):
    rid = new_receipt(api)
    api.patch(f"/api/receipts/{rid}", json={"fields": {"merchant_name": "직접 입력"}}, headers=EMP)
    process(rid, f"incoming/{rid}.jpg")
    ai = set(api.get(f"/api/receipts/{rid}", headers=EMP).json()["ai_filled"])
    assert "total_amount" in ai and "category" in ai  # mock extraction suggests 식사·간식비
    assert "merchant_name" not in ai  # the employee typed it before the model finished

    api.patch(f"/api/receipts/{rid}", json={"fields": {"total_amount": 13500}}, headers=EMP)
    assert "total_amount" not in api.get(f"/api/receipts/{rid}", headers=EMP).json()["ai_filled"]

    # Picking the suggested category in the chat confirms it: no longer an AI guess.
    sse_done(chat.post(f"/chat/receipts/{rid}/turn", json={}, headers=EMP))
    sse_done(chat.post(f"/chat/receipts/{rid}/turn", json={"message": "팀 회의 다과"}, headers=EMP))
    sse_done(chat.post(f"/chat/receipts/{rid}/turn", json={"message": "식사·간식비"}, headers=EMP))
    after = api.get(f"/api/receipts/{rid}", headers=EMP).json()
    assert after["fields"]["category"] == "food" and "category" not in after["ai_filled"]
