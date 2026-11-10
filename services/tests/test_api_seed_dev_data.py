"""scripts/seed_dev_data.py: the demo data reads as real receipts through the API (needs pillow)."""

import sys
from pathlib import Path

import pytest
from conftest import REV

pytest.importorskip("PIL")
sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))


def test_seed_tells_the_whole_flow_up_to_a_given_moment(api, monkeypatch):
    import clear_dev_data
    import seed_dev_data
    from receiptflow_common import store

    monkeypatch.setattr(sys, "argv", ["seed", "--as-of", "2026-11-14T11:00", "--count", "60"])
    seed_dev_data.main()

    by_status = {
        s: api.get(f"/api/review/receipts?status={s}", headers=REV).json()["items"]
        for s in ("draft", "submitted", "changes_requested", "approved")
    }
    assert sum(len(v) for v in by_status.values()) == 60
    assert all(len(v) >= 4 for v in by_status.values())
    everything = [r for items in by_status.values() for r in items]
    # nothing happens after the given moment, and nothing was written before it was bought
    assert max(r["updated_at"] for r in everything) < "2026-11-14T11:00"
    assert all(r["fields"]["transaction_at"] < r["created_at"][:16] for r in everything)
    # what the app itself guarantees: an amount error is never submitted, a sent-back receipt says why
    for r in everything:
        errors = [c for c in r["checks"] if c["level"] == "error"]
        assert not errors or r["review_status"] == "draft"
    assert all(r["review_note"] and r["review_fields"] for r in by_status["changes_requested"])
    codes = {p["code"] for r in by_status["submitted"] for p in r["review_points"]}
    assert {"duplicate", "same_approval", "late_night"} <= codes

    # one receipt went back and forth: its history and chat show every step in order
    def actions(r):
        return [e["action"] for e in store.list_events(r["id"])]

    fixed = [r for r in by_status["approved"] if "changes_requested" in actions(r)]
    assert fixed
    steps = [a for a in actions(fixed[0]) if a in ("submitted", "changes_requested", "approved")]
    assert steps == ["submitted", "changes_requested", "submitted", "approved"]
    chats = [store.list_messages(r["id"]) for r in everything]
    assert all(m[0]["role"] == "assistant" and m[0]["suggestions"] for m in chats)
    assert len({len(m) for m in chats}) >= 4  # not one script for every receipt
    assert any(m.get("event") == "changes_requested" for chat in chats for m in chat)

    clear_dev_data.main()
    assert api.get("/api/review/receipts?status=approved", headers=REV).json()["items"] == []
