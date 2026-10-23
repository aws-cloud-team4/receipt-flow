"""End-to-end across services: create → upload → worker → chat → edit → submit → review."""

import pytest
from conftest import EMP, REV
from helpers import new_receipt, sse_done
from ocr_worker.main import process
from receiptflow_common import store
from receiptflow_common.auth import authenticate


@pytest.mark.parametrize(
    "headers",
    [REV, {"Authorization": "Bearer dev:adm-1:admin:admin"}],
    ids=["reviewer", "admin"],
)
def test_non_employee_cannot_write_receipts_even_when_owner(api, chat, pre, headers):
    user = authenticate(headers["Authorization"].split(" ", 1)[1])
    # A receipt owned before a role change must not bypass the role restriction.
    receipt = store.create_receipt(user.sub, user.name, "server", user.profile())
    rid = receipt["id"]
    before = store.get_receipt(rid)
    requests = [
        ("POST", "/api/receipts", None),
        ("GET", "/api/receipts", None),
        ("POST", f"/api/receipts/{rid}/upload-url", None),
        ("POST", f"/api/receipts/{rid}/uploaded", None),
        ("PATCH", f"/api/receipts/{rid}", {"fields": {"purpose": "권한 검사"}}),
        ("POST", f"/api/receipts/{rid}/submit", None),
        ("DELETE", f"/api/receipts/{rid}", None),
    ]
    for method, path, body in requests:
        response = api.request(method, path, headers=headers, json=body)
        assert response.status_code == 403, (method, path, response.text)
        assert response.json()["error"]["code"] == "forbidden"
    assert (
        chat.post(f"/chat/receipts/{rid}/turn", headers=headers, json={"message": "목적 변경"}).status_code
        == 403
    )
    assert pre.post(f"/preprocess/receipts/{rid}/detect", headers=headers).status_code == 403
    assert (
        pre.post(f"/preprocess/receipts/{rid}/apply", headers=headers, json={"corners": None}).status_code
        == 403
    )
    assert store.get_receipt(rid) == before
    assert store.list_messages(rid) == []
    assert api.get("/api/me", headers=headers).status_code == 200
    assert api.get("/api/meta", headers=headers).status_code == 200
    if user.is_admin:
        assert api.get(f"/api/receipts/{rid}", headers=headers).status_code == 403
        assert chat.get(f"/chat/receipts/{rid}/messages", headers=headers).status_code == 403
        assert api.get("/api/admin/receipts?status=draft", headers=headers).status_code == 200
        assert api.get("/api/review/receipts", headers=headers).status_code == 403
    else:
        assert api.get(f"/api/receipts/{rid}", headers=headers).status_code == 200
        assert chat.get(f"/chat/receipts/{rid}/messages", headers=headers).status_code == 200
        assert api.get("/api/review/receipts?status=draft", headers=headers).status_code == 200
        assert api.get("/api/admin/receipts?status=draft", headers=headers).status_code == 403


def test_full_flow(api, chat):
    rid = new_receipt(api)

    # Department comes from the login profile (dev user kim = 영업부 대리).
    created = api.get(f"/api/receipts/{rid}", headers=EMP).json()
    assert created["fields"]["department"] == "영업부"
    assert created["owner_profile"] == {
        "employee_no": "SAL2026901",
        "department": "영업부",
        "position": "대리",
    }

    # Chat starts while analysis is still queued: purpose, then a category from fixed choices.
    first = sse_done(chat.post(f"/chat/receipts/{rid}/turn", json={}, headers=EMP))
    assert first["slot"] == "purpose" and first["suggestions"][0]["category_label"]
    second = sse_done(
        chat.post(f"/chat/receipts/{rid}/turn", json={"message": "고객 미팅 점심"}, headers=EMP)
    )
    assert second["slot"] == "category" and second["choices"][:2] == ["식사·간식비", "접대·선물비"]
    done = sse_done(chat.post(f"/chat/receipts/{rid}/turn", json={"message": "식사·간식비"}, headers=EMP))
    assert done["fields"]["category"] == "food"
    assert done["slot"] == "wait_analysis"  # department comes from the profile, never asked

    assert process(rid, f"incoming/{rid}.jpg") is True
    receipt = api.get(f"/api/receipts/{rid}", headers=EMP).json()
    assert receipt["analysis_status"] == "done"
    assert receipt["fields"]["merchant_name"] == "스타벅스 강남R점"
    assert receipt["fields"]["purpose"] == "고객 미팅 점심"
    assert receipt["fields"]["category"] == "food"  # the employee's choice beats the AI suggestion
    assert receipt["image_url"]
    assert receipt["timings"]["chat_first_question"] and receipt["timings"]["analysis_finished"]

    final = sse_done(chat.post(f"/chat/receipts/{rid}/turn", json={}, headers=EMP))
    assert final["finished"] is True

    assert api.post(f"/api/receipts/{rid}/submit", headers=EMP).status_code == 200
    assert (
        api.patch(f"/api/receipts/{rid}", json={"fields": {"purpose": "x"}}, headers=EMP).status_code == 409
    )

    queue = api.get("/api/review/receipts?status=submitted", headers=REV).json()["items"]
    assert [r["id"] for r in queue] == [rid]
    assert api.post(
        f"/api/review/receipts/{rid}/request-changes", json={"reason": "목적을 자세히"}, headers=REV
    ).is_success

    receipt = api.get(f"/api/receipts/{rid}", headers=EMP).json()
    assert receipt["review_status"] == "changes_requested" and receipt["review_note"] == "목적을 자세히"
    assert api.patch(
        f"/api/receipts/{rid}", json={"fields": {"purpose": "A사 제안 미팅 점심"}}, headers=EMP
    ).is_success
    assert api.post(f"/api/receipts/{rid}/submit", headers=EMP).is_success
    assert api.post(f"/api/review/receipts/{rid}/approve", headers=REV).is_success
    assert api.post(f"/api/review/receipts/{rid}/approve", headers=REV).status_code == 409

    history = [e["action"] for e in api.get(f"/api/receipts/{rid}", headers=EMP).json()["history"]]
    assert history == ["created", "submitted", "changes_requested", "submitted", "approved"]

    csv = api.get("/api/review/export.csv?month=2026-10", headers=REV).text
    assert (
        "스타벅스 강남R점" in csv
        and "SAL2026901" in csv
        and ",식사·간식비," in csv
        and "검수자" in csv
        and "승인" in csv
    )


@pytest.mark.parametrize("requested_fields", [["purpose"], []])
def test_review_points_and_the_change_request_round_trip(api, chat, requested_fields):
    rid = new_receipt(api)
    process(rid, f"incoming/{rid}.jpg")
    fields = {"purpose": "점심", "category": "entertainment", "payment_method": "체크카드"}
    api.patch(f"/api/receipts/{rid}", json={"fields": fields}, headers=EMP)
    assert api.post(f"/api/receipts/{rid}/submit", headers=EMP).status_code == 200

    detail = api.get(f"/api/receipts/{rid}", headers=REV).json()["review_points"]
    by_code = {p["code"]: p for p in detail}
    assert by_code["entertainment"]["fields"] == ["purpose"]
    assert by_code["edited_fields"]["fields"] == ["payment_method"]  # the web turns these into a request
    assert by_code["result_unconfirmed"]["fields"] == []
    points = [p["text"] for p in detail]
    assert any("접대·선물비" in t for t in points)
    assert any("직접 입력·수정한 칸 결제수단" in t for t in points)  # the employee changed what the AI read
    assert any("결과 확인을 건너뛰" in t for t in points)
    listed = api.get("/api/review/receipts?status=submitted", headers=REV).json()["items"]
    assert next(r for r in listed if r["id"] == rid)["review_points"]

    bad = api.post(
        f"/api/review/receipts/{rid}/request-changes", json={"reason": "x", "fields": ["nope"]}, headers=REV
    )
    assert bad.status_code == 400
    reason = {"reason": "접대 상대(거래처)를 지출 목적에 적어 주세요.", "fields": requested_fields}
    sent = api.post(f"/api/review/receipts/{rid}/request-changes", json=reason, headers=REV).json()
    assert sent["review_status"] == "changes_requested" and sent["review_fields"] == requested_fields

    told = sse_done(chat.post(f"/chat/receipts/{rid}/turn", json={"event": "changes_requested"}, headers=EMP))
    assert (
        "보완을 요청했어요" in told["text"]
        and "지출 목적" in told["text"]
        and told["choices"] == ["직접 수정"]
    )
    assert "[제출하기]" in told["text"] and "[수정 완료]" not in told["text"]
    again = sse_done(
        chat.post(f"/chat/receipts/{rid}/turn", json={"event": "changes_requested"}, headers=EMP)
    )
    assert again["repeat"]  # once per request

    api.patch(f"/api/receipts/{rid}", json={"fields": {"purpose": "A사 담당자 점심 접대"}}, headers=EMP)
    assert api.post(f"/api/receipts/{rid}/submit", headers=EMP).json()["review_status"] == "submitted"
