"""Explaining a check instead of fixing it (docs/contract.md "점검 사유")."""

from conftest import EMP, REV
from helpers import new_receipt
from ocr_worker.main import process


def _analysed(api, **fields) -> tuple[str, dict]:
    rid = new_receipt(api)
    process(rid, f"incoming/{rid}.jpg")
    body = {"purpose": "팀 회의 간식", "category": "식사·간식비", **fields}
    return rid, api.patch(f"/api/receipts/{rid}", json={"fields": body}, headers=EMP).json()


def _note(api, rid: str, code: str, note: str | None):
    path = f"/api/receipts/{rid}/checks/{code}/note"
    return api.delete(path, headers=EMP) if note is None else api.put(path, json={"note": note}, headers=EMP)


def test_explained_amount_mismatch_can_be_submitted_and_reviewer_sees_why(api):
    rid, receipt = _analysed(api, total_amount=14000)
    assert [c["code"] for c in receipt["checks"]] == ["amount_mismatch"]
    assert api.post(f"/api/receipts/{rid}/submit", headers=EMP).json()["error"]["code"] == "check_failed"

    receipt = _note(api, rid, "amount_mismatch", "  쿠폰 1,200원 사용  ").json()
    assert receipt["checks"][0]["note"] == "쿠폰 1,200원 사용" and receipt["checks"][0]["level"] == "error"
    assert receipt["check_notes"]["amount_mismatch"]["by"] == "employee"
    assert api.post(f"/api/receipts/{rid}/submit", headers=EMP).json()["review_status"] == "submitted"

    points = api.get(f"/api/receipts/{rid}", headers=REV).json()["review_points"]
    point = next(p for p in points if p["code"] == "amount_mismatch")
    assert point["level"] == "warn" and point["text"].endswith("직원 사유: 쿠폰 1,200원 사용")


def test_reason_drops_when_the_amount_changes(api):
    rid, _ = _analysed(api, total_amount=14000)
    _note(api, rid, "amount_mismatch", "쿠폰 사용")
    receipt = api.patch(f"/api/receipts/{rid}", json={"fields": {"total_amount": 15000}}, headers=EMP).json()
    assert receipt["checks"][0].get("note") is None and receipt["check_notes"] == {}
    assert api.post(f"/api/receipts/{rid}/submit", headers=EMP).json()["error"]["code"] == "check_failed"
    # an unrelated edit keeps a reason that still fits
    _note(api, rid, "amount_mismatch", "쿠폰 사용")
    receipt = api.patch(
        f"/api/receipts/{rid}", json={"fields": {"purpose": "팀 회의 다과"}}, headers=EMP
    ).json()
    assert receipt["checks"][0]["note"] == "쿠폰 사용"


def test_warning_reason_can_be_removed(api):
    rid, receipt = _analysed(api, transaction_at="2026-10-17T12:31")  # a Saturday
    assert [c["code"] for c in receipt["checks"]] == ["weekend"]
    assert _note(api, rid, "weekend", "주말 행사 지원").json()["checks"][0]["note"] == "주말 행사 지원"
    assert "note" not in _note(api, rid, "weekend", None).json()["checks"][0]


def test_reasons_are_refused_when_they_do_not_apply(api):
    rid, _ = _analysed(api)
    assert _note(api, rid, "bad_date", "괜찮아요").json()["error"]["code"] == "not_notable"
    assert _note(api, rid, "weekend", "주말 행사").json()["error"]["code"] == "check_not_found"
    assert _note(api, rid, "weekend", "   ").json()["error"]["code"] == "invalid_request"
    assert _note(api, rid, "weekend", "가" * 201).json()["error"]["code"] == "invalid_request"
    other = api.put(f"/api/receipts/{rid}/checks/weekend/note", json={"note": "x"}, headers=REV)
    assert other.status_code == 403
