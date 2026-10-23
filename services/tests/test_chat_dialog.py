"""chat-service: scripted (mock) dialog — result card, suggestion and card buttons."""

from conftest import EMP
from helpers import new_receipt, sse_done
from ocr_worker.main import process
from receiptflow_common import store


def test_result_card_buttons_in_mock_chat(api, chat):
    rid = new_receipt(api)
    process(rid, f"incoming/{rid}.jpg")
    sse_done(chat.post(f"/chat/receipts/{rid}/turn", json={"event": "analysis_done"}, headers=EMP))
    # "직접 수정" is a card button, not the purpose answer
    sse_done(chat.post(f"/chat/receipts/{rid}/turn", json={"message": "직접 수정"}, headers=EMP))
    r = store.get_receipt(rid)
    assert not r["fields"].get("purpose") and not r.get("result_confirmed_at")
    sse_done(chat.post(f"/chat/receipts/{rid}/turn", json={"message": "맞아요"}, headers=EMP))
    assert store.get_receipt(rid)["result_confirmed_at"]
    process(rid, f"incoming/{rid}.jpg")  # read again (new photo) → confirm again
    assert store.get_receipt(rid)["result_confirmed_at"] is None


def test_suggestion_button_saves_purpose_and_category(api, chat):
    rid = new_receipt(api)
    process(rid, f"incoming/{rid}.jpg")
    first = sse_done(chat.post(f"/chat/receipts/{rid}/turn", json={}, headers=EMP))
    pick = first["suggestions"][0]
    assert pick["category"] == "food"  # examples that fit the extracted category come first
    history = chat.get(f"/chat/receipts/{rid}/messages", headers=EMP).json()["items"]
    assert history[-1]["suggestions"] == first["suggestions"]  # buttons come back on reload

    done = sse_done(chat.post(f"/chat/receipts/{rid}/turn", json={"choice": pick}, headers=EMP))
    assert done["actions"] == ["submit"] and done["changed"]
    last = chat.get(f"/chat/receipts/{rid}/messages", headers=EMP).json()["items"][-1]
    assert last["actions"] == ["submit"]  # the review card comes back at this point after a reload
    r = store.get_receipt(rid)
    assert r["fields"]["purpose"] == pick["purpose"] and r["fields"]["category"] == "food"
    assert "category" not in r["ai_filled"]
    assert store.list_events(rid)[-1]["action"] == "edited"

    bad = chat.post(
        f"/chat/receipts/{rid}/turn", json={"choice": {"purpose": "x", "category": "snacks"}}, headers=EMP
    )
    assert bad.status_code == 400


def test_card_buttons_keep_open_suggestions(api, chat):
    rid = new_receipt(api)
    process(rid, f"incoming/{rid}.jpg")
    first = sse_done(chat.post(f"/chat/receipts/{rid}/turn", json={"event": "analysis_done"}, headers=EMP))
    assert first["suggestions"]
    ok = sse_done(chat.post(f"/chat/receipts/{rid}/turn", json={"message": "맞아요"}, headers=EMP))
    assert ok["suggestions"] == first["suggestions"]  # the purpose question is still open
    assert ok["text"].startswith("확인했어요") and store.get_receipt(rid)["result_confirmed_at"]
