"""AI assistant tools and turn loop, with a scripted model (no Bedrock)."""

from chat_service import agent
from conftest import EMP
from helpers import new_receipt
from ocr_worker.main import process
from receiptflow_common import store
from receiptflow_common.auth import authenticate

USER = authenticate(EMP["Authorization"].split(" ", 1)[1])


def analysed(api) -> dict:
    rid = new_receipt(api)
    process(rid, f"incoming/{rid}.jpg")
    return store.get_receipt(rid)


def test_update_fields_changes_only_editable_fields_and_logs(api):
    st = agent.TurnState(receipt=analysed(api), user=USER)
    result, summary = agent.run_tool(
        "update_fields", {"fields": {"payment_method": "체크카드", "department": "개발팀"}}, st
    )
    assert (
        result["ok"]
        and result["updated"] == {"결제수단": {"before": "신용카드", "after": "체크카드"}}
        and result["not_changed"] == ["department"]
    )
    assert summary and st.changed
    r = store.get_receipt(st.receipt["id"])
    assert r["fields"]["payment_method"] == "체크카드" and r["fields"]["department"] == "영업부"
    assert "payment_method" not in r["ai_filled"]  # the person said it
    assert [e["action"] for e in store.list_events(r["id"])][-1] == "ai_edited"

    blocked, _ = agent.run_tool("update_fields", {"fields": {"department": "개발팀"}}, st)
    assert blocked["ok"] is False


def test_category_suggestion_vs_user_choice(api):
    st = agent.TurnState(receipt=analysed(api), user=USER)
    _, summary = agent.run_tool("set_category", {"code": "entertainment", "confirmed_by_user": False}, st)
    assert summary is None  # a suggestion is asked about, not announced as decided
    assert "category" in store.get_receipt(st.receipt["id"])["ai_filled"]
    _, summary = agent.run_tool("set_category", {"code": "food", "confirmed_by_user": True}, st)
    assert summary == "지출 분류를 식사·간식비로 정했어요"
    r = store.get_receipt(st.receipt["id"])
    assert r["fields"]["category"] == "food" and "category" not in r["ai_filled"]
    bad, _ = agent.run_tool("set_category", {"code": "snacks", "confirmed_by_user": True}, st)
    assert bad["ok"] is False


def test_same_value_again_changes_nothing(api):
    st = agent.TurnState(receipt=analysed(api), user=USER)
    _, summary = agent.run_tool("update_fields", {"fields": {"purpose": "거래처 회의 간식 구매"}}, st)
    assert summary == "지출 목적 거래처 회의 간식 구매로 고쳤어요"
    events = len(store.list_events(st.receipt["id"]))
    result, summary = agent.run_tool("update_fields", {"fields": {"purpose": "거래처 회의 간식 구매"}}, st)
    assert result == {"ok": True, "unchanged": True} and summary is None
    assert len(store.list_events(st.receipt["id"])) == events


def test_ai_category_needs_a_yes_before_submission(api):
    st = agent.TurnState(receipt=analysed(api), user=USER)
    agent.run_tool("update_fields", {"fields": {"purpose": "회의 간식"}}, st)
    agent.run_tool("set_category", {"code": "food", "confirmed_by_user": False}, st)
    result, _ = agent.run_tool("check_submission", {}, st)
    assert result["ready"] is False and result["unconfirmed"] == ["지출 분류"] and st.actions == []
    agent.run_tool("set_category", {"code": "food", "confirmed_by_user": True}, st)
    result, _ = agent.run_tool("check_submission", {}, st)
    assert result["ready"] is True and result["unconfirmed"] == [] and st.actions == ["submit"]


def test_check_submission_and_confirm(api):
    st = agent.TurnState(receipt=analysed(api), user=USER)
    result, _ = agent.run_tool("check_submission", {}, st)
    assert result["ready"] is False and "지출 목적" in result["missing"] and st.actions == []
    agent.run_tool("update_fields", {"fields": {"purpose": "팀 회의 다과"}}, st)
    agent.run_tool("set_category", {"code": "food", "confirmed_by_user": True}, st)
    result, _ = agent.run_tool("check_submission", {}, st)
    assert result["ready"] is True and st.actions == ["submit"]
    agent.run_tool("confirm_result", {}, st)
    assert store.get_receipt(st.receipt["id"])["result_confirmed_at"]


def test_context_includes_items_and_similar_receipts(api):
    first = analysed(api)
    store.apply_fields(first, {"purpose": "팀 회의 다과", "category": "food"})
    second = analysed(api)
    text = agent.context(second, USER)
    assert "아메리카노" in text  # item summary from extraction
    assert "팀 회의 다과" in text  # same merchant earlier
    assert "영업부" in text


def test_context_names_the_time_of_day(api):
    assert agent.time_of_day("2026-10-14T12:57") == "점심 (12시 57분)"
    assert agent.time_of_day("2026-10-14T02:05") == "새벽 (2시 5분)"
    assert agent.time_of_day("2026-10-14T19:30") == "저녁 (19시 30분)"
    assert agent.time_of_day(None) is None
    r = analysed(api)
    r = store.apply_fields(r, {"transaction_at": "2026-10-14T12:57"})
    assert '"거래 시간대": "점심 (12시 57분)"' in agent.context(r, USER)


def test_history_alternates_and_starts_with_user():
    msgs = agent.history_messages(
        [
            {"role": "assistant", "text": "안녕하세요"},
            {"role": "event", "text": "analysis_done", "event": "analysis_done"},
            {"role": "user", "text": "맞아요"},
        ]
    )
    assert [m["role"] for m in msgs] == ["user", "assistant", "user"]
    assert "분석이 끝났습니다" in msgs[2]["content"][0]["text"] and "맞아요" in msgs[2]["content"][0]["text"]


def test_turn_loop_runs_tools_then_answers(api, monkeypatch):
    receipt = analysed(api)
    calls = []

    def fake_stream(messages, system):
        calls.append(messages)
        if len(calls) == 1:
            yield "text", "결제수단을 고칠게요."
            use = {
                "toolUseId": "t1",
                "name": "update_fields",
                "input": {"fields": {"payment_method": "체크카드"}},
            }
            yield "message", ([{"text": "결제수단을 고칠게요."}, {"toolUse": use}], "tool_use")
        else:
            assert messages[-1]["content"][0]["toolResult"]["toolUseId"] == "t1"
            yield "text", "체크카드로 바꿨어요."
            yield "message", ([{"text": "체크카드로 바꿨어요."}], "end_turn")

    monkeypatch.setattr(agent, "_stream", fake_stream)
    events = list(agent.run_turn(receipt, USER, [{"role": "user", "text": "결제는 체크카드였어"}]))
    kinds = [k for k, _ in events]
    assert kinds.count("tool") == 1 and kinds[-1] == "done"
    state, text = events[-1][1]
    assert state.changed and text == "체크카드로 바꿨어요."  # only the final round is the reply
    assert store.get_receipt(receipt["id"])["fields"]["payment_method"] == "체크카드"


def test_suggest_expense_keeps_valid_pairs_and_ends_turn(api, monkeypatch):
    receipt = analysed(api)
    st = agent.TurnState(receipt=receipt, user=USER)
    agent.run_tool(
        "suggest_expense",
        {
            "suggestions": [
                {"purpose": "팀 회의 다과", "category": "food"},
                {"purpose": "팀 회의 다과", "category": "travel"},  # repeat
                {"purpose": "간식", "category": "snacks"},  # not a category
                {"purpose": "고객 미팅 다과", "category": "food"},
            ]
        },
        st,
    )
    assert [s["purpose"] for s in st.suggestions] == ["팀 회의 다과", "고객 미팅 다과"]
    assert st.suggestions[0]["category_label"] == "식사·간식비"

    calls = []

    def fake_stream(messages, system):
        calls.append(1)
        use = {"toolUseId": "t1", "name": "suggest_expense", "input": {"suggestions": []}}
        yield "text", "지출 목적과 분류를 알려 주세요."
        yield "message", ([{"text": "지출 목적과 분류를 알려 주세요."}, {"toolUse": use}], "tool_use")

    monkeypatch.setattr(agent, "_stream", fake_stream)
    events = list(agent.run_turn(receipt, USER, [{"role": "user", "text": "안녕"}]))
    assert len(calls) == 1 and events[-1][1][1] == "지출 목적과 분류를 알려 주세요."  # no extra round


def test_claimed_change_without_tool_is_retried(api, monkeypatch):
    receipt = analysed(api)
    calls = []

    def fake_stream(messages, system):
        calls.append(messages[-1]["content"][0])
        if len(calls) == 1:
            yield "message", ([{"text": "결제수단을 바꿨어요."}], "end_turn")
        elif len(calls) == 2:
            assert "시스템 점검" in calls[-1]["text"]
            use = {
                "toolUseId": "t1",
                "name": "update_fields",
                "input": {"fields": {"payment_method": "체크카드"}},
            }
            yield "message", ([{"toolUse": use}], "tool_use")
        else:
            yield "message", ([{"text": "체크카드로 바꿨어요."}], "end_turn")

    monkeypatch.setattr(agent, "_stream", fake_stream)
    events = list(agent.run_turn(receipt, USER, [{"role": "user", "text": "결제는 체크카드였어"}]))
    state, text = events[-1][1]
    assert len(calls) == 3 and state.changed and text == "체크카드로 바꿨어요."
    assert store.get_receipt(receipt["id"])["fields"]["payment_method"] == "체크카드"


def test_english_or_reasoning_reply_is_rewritten(api, monkeypatch):
    receipt = analysed(api)
    replies = iter(
        [
            "The analysis is done, so I'll suggest purposes.",
            "사용자가 목적을 말하지 않았으므로 추천합니다.",
        ]
    )

    def fake_stream(messages, system):
        text = next(replies)
        use = {"toolUseId": "t1", "name": "suggest_expense", "input": {"suggestions": []}}
        yield "message", ([{"text": text}, {"toolUse": use}], "tool_use")

    monkeypatch.setattr(agent, "_stream", fake_stream)
    events = list(agent.run_turn(receipt, USER, [{"role": "user", "text": "안녕"}]))
    # one retry, still not right → a safe fixed reply instead of the model's notes
    assert events[-1][1][1] == "확인했어요. 더 필요한 게 있으면 말씀해 주세요."
    assert agent._voice_ok("지출 목적과 분류를 알려 주세요.")


def test_english_never_reaches_the_screen(api, monkeypatch):
    receipt = analysed(api)
    rounds = iter(["The receipt looks like a duplicate, so I will ask.", "중복 증빙인지 확인해 주세요."])

    def fake_stream(messages, system):
        text = next(rounds)
        for i in range(0, len(text), 5):
            yield "text", text[i : i + 5]
        yield "message", ([{"text": text}], "end_turn")

    monkeypatch.setattr(agent, "_stream", fake_stream)
    events = list(agent.run_turn(receipt, USER, [{"role": "user", "text": "중복이야?"}]))
    shown = "".join(v for k, v in events if k == "delta")
    assert "receipt" not in shown and "중복 증빙인지 확인해 주세요." in shown
    assert events[-1][1][1] == "중복 증빙인지 확인해 주세요."


def test_result_is_confirmed_before_the_purpose_question(api, chat, monkeypatch):
    from types import SimpleNamespace

    from chat_service import main
    from helpers import sse_done

    monkeypatch.setattr(main, "get_settings", lambda: SimpleNamespace(ai_mode="bedrock"))
    pick = {"purpose": "팀 회의 다과", "category": "food"}

    def fake_stream(messages, system):
        use = {"toolUseId": "t1", "name": "suggest_expense", "input": {"suggestions": [pick]}}
        yield "message", ([{"text": "추천을 준비했습니다."}, {"toolUse": use}], "tool_use")

    monkeypatch.setattr(agent, "_stream", fake_stream)
    rid = analysed(api)["id"]
    first = sse_done(chat.post(f"/chat/receipts/{rid}/turn", json={"event": "analysis_done"}, headers=EMP))
    assert first["text"] == "영수증을 읽었어요. 내용이 맞는지 확인해 주세요." and first["suggestions"] == []
    assert (
        chat.get(f"/chat/receipts/{rid}/messages", headers=EMP).json()["items"][-1].get("suggestions") is None
    )

    fix = sse_done(chat.post(f"/chat/receipts/{rid}/turn", json={"message": "직접 수정"}, headers=EMP))
    assert fix["choices"] == ["수정 완료"] and fix["suggestions"] == []
    done = sse_done(chat.post(f"/chat/receipts/{rid}/turn", json={"message": "수정 완료"}, headers=EMP))
    assert done["text"].endswith("어떤 일로 쓰신 비용인가요?") and "비어 있" not in done["text"]
    assert done["suggestions"][0]["purpose"] == "팀 회의 다과"  # the ones prepared with the result
    assert store.get_receipt(rid)["result_confirmed_at"]


def test_warning_hint_names_the_day_and_hour():
    from chat_service.main import _warning_hint

    receipt = {
        "fields": {"transaction_at": "2026-10-17T23:40"},  # a Saturday
        "checks": [{"code": "late_night"}, {"code": "weekend"}],
    }
    assert _warning_hint(receipt) == "토요일 밤 11시 결제라 사유를 목적에 함께 적어 두면 좋아요."
