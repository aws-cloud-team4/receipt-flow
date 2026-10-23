"""api-service: the public usage card — one Budgets read a day, at 09:00 KST."""

from datetime import datetime

from api_service import usage
from receiptflow_common.org import KST


def test_snapshot_day_turns_over_at_nine():
    assert usage.snapshot_day(datetime(2026, 10, 18, 8, 59, tzinfo=KST)).isoformat() == "2026-10-17"
    assert usage.snapshot_day(datetime(2026, 10, 18, 9, 0, tzinfo=KST)).isoformat() == "2026-10-18"


def test_public_usage_reads_the_budget_once_a_day(api, monkeypatch):
    calls = []

    def fake_budget():
        calls.append(1)
        return {"spent": 11.0, "limit": 200.0, "start": "2026-10-01", "end": "2026-11-14"}

    monkeypatch.setattr(usage, "read_budget", fake_budget)
    first = api.get("/api/public/usage")  # no login needed
    assert first.status_code == 200
    body = first.json()
    assert body["spent"] == 11 and body["limit"] == 200 and body["remaining"] == 189
    assert body["percent"] == 5.5 and body["currency"] == "USD" and body["label"]
    assert body["as_of"].endswith("09:00:00+09:00")
    assert api.get("/api/public/usage").json()["spent"] == 11
    assert len(calls) == 1  # the second request used the stored snapshot


def test_public_usage_unavailable_hides_the_card(api, monkeypatch):
    def broken():
        raise RuntimeError("AccessDenied")

    monkeypatch.setattr(usage, "read_budget", broken)
    resp = api.get("/api/public/usage")
    assert resp.status_code == 503 and resp.json()["error"]["code"] == "usage_unavailable"
