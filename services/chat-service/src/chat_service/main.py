import json
import logging
from collections.abc import Iterator
from typing import Any, Literal

from fastapi import Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from receiptflow_common import store
from receiptflow_common.auth import User, current_user, employee_only
from receiptflow_common.bedrock import ModelError
from receiptflow_common.config import get_settings
from receiptflow_common.domain import (
    CATEGORIES,
    EDITABLE_STATUSES,
    FIELD_LABELS,
    missing_required,
    normalize_fields,
    now_iso,
    parse_transaction_at,
    to_category,
)
from receiptflow_common.errors import ApiError, forbidden, not_found
from receiptflow_common.webapp import create_app

from . import agent
from .dialog import Parsed, mock_suggestions, next_reply, parse_answer, suggestions

log = logging.getLogger("chat-service")
app = create_app("receipt-flow chat-service")


class Choice(BaseModel):
    purpose: str = Field(min_length=1, max_length=100)
    category: str


class Turn(BaseModel):
    message: str | None = Field(default=None, max_length=1000)
    event: Literal["start", "analysis_done", "changes_requested"] | None = None
    choice: Choice | None = None  # a suggestion button: saved as is, no model call


EDIT_REPLIES = ("직접 수정", "고칠게요")  # "고칠게요": the earlier label, still accepted
EDITED_REPLIES = ("수정 완료", "다 고쳤어요")
CARD_REPLIES = ("맞아요", *EDIT_REPLIES, *EDITED_REPLIES)
WEEKDAYS = "월화수목금토일"


def _load(receipt_id: str, user: User, *, owner_only: bool) -> dict[str, Any]:
    if user.is_admin:
        raise forbidden()
    receipt = store.get_receipt(receipt_id)
    if not receipt:
        raise not_found()
    if receipt["owner_sub"] != user.sub and (owner_only or not user.is_reviewer):
        raise forbidden()
    return receipt


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _chunks(text: str, size: int = 6) -> Iterator[str]:
    for i in range(0, len(text), size):
        yield text[i : i + size]


def _done(text: str, receipt: dict[str, Any], **extra: Any) -> dict[str, Any]:
    return {
        "text": text,
        "slot": None,
        "choices": [],
        "suggestions": [],
        "actions": [],
        "changed": False,
        "repeat": False,
        "finished": False,
        **extra,
        "fields": receipt.get("fields", {}),
    }


def _choice_turn(receipt: dict[str, Any], user: User, choice: Choice) -> StreamingResponse:
    """The employee picked a purpose · category suggestion: save both, answer without the model."""
    code = to_category(choice.category)
    if not code:
        allowed = ", ".join(CATEGORIES.values())
        raise ApiError(400, "invalid_category", f"지출 분류는 {allowed} 중 하나입니다.")
    rid = receipt["id"]
    purpose = choice.purpose.strip()
    store.add_message(rid, "user", f"{purpose} · {CATEGORIES[code]}")
    values = {"purpose": purpose, "category": code}
    receipt = store.apply_fields(
        receipt,
        values,
        ai_filled=[k for k in receipt.get("ai_filled", []) if k not in values],  # the person chose these
        timings={"chat_last_answer": now_iso()},
    )
    note = f"AI 추천 선택: 지출 목적 {purpose}, 지출 분류 {CATEGORIES[code]}"
    store.add_event(rid, user.name, "edited", note)
    text, actions = _next_step(receipt)
    text = f"목적과 분류를 정했어요. {text}"
    # slot "category": the mock dialog treats the category as confirmed and does not ask again.
    # actions are kept with the message so the review card stays at this point of the conversation
    store.add_message(rid, "assistant", text, slot="category", **({"actions": actions} if actions else {}))
    return _reply(text, _done(text, receipt, slot="category", actions=actions, changed=True))


def _next_step(receipt: dict[str, Any]) -> tuple[str, list[str]]:
    """What is left once purpose and category are set: (sentence, screen actions)."""
    missing = [FIELD_LABELS[k] for k in missing_required(receipt.get("fields", {}))]
    if receipt["analysis_status"] in ("waiting", "queued", "processing"):
        return "분석이 끝나면 확인할 내용을 알려 드릴게요.", []
    if missing:
        return f"{', '.join(missing)}은(는) 아래에서 채워 주세요.", []
    if any(c["level"] == "error" for c in receipt.get("checks", [])):
        return "점검 결과에 오류가 있어 먼저 확인해 주세요.", []
    return "제출할 내용을 확인해 주세요.", ["submit"]  # the screen shows the final review card


def _reply(text: str, done: dict[str, Any]) -> StreamingResponse:
    def stream() -> Iterator[str]:
        yield _sse("delta", {"text": text})
        yield _sse("done", done)

    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


def _object_particle(word: str) -> str:
    """을/를 after a Korean word (을 after a final consonant)."""
    last = word[-1] if word else ""
    if "가" <= last <= "힣":
        return "을" if (ord(last) - 0xAC00) % 28 else "를"
    return "을(를)"


def _changes_turn(receipt: dict[str, Any]) -> StreamingResponse:
    """The reviewer sent it back: say why and lead to what to fix (fixed words, once per request)."""
    rid = receipt["id"]
    if receipt["review_status"] != "changes_requested":
        return _reply("", _done("", receipt, repeat=True))
    reviewed_at = receipt.get("reviewed_at")
    if any(
        m.get("event") == "changes_requested" and m.get("reviewed_at") == reviewed_at
        for m in store.list_messages(rid)
    ):
        return _reply("", _done("", receipt, repeat=True))  # already told for this request
    store.add_message(rid, "event", "changes_requested", event="changes_requested", reviewed_at=reviewed_at)
    who = receipt.get("reviewed_by") or "담당자"
    text = f"{who}님이 보완을 요청했어요: “{receipt.get('review_note') or ''}”"
    fields = [k for k in receipt.get("review_fields") or [] if k in FIELD_LABELS]
    if "photo" in (receipt.get("review_fields") or []):
        text += " 사진을 다시 찍어 올려 주세요. 다시 올리면 처음부터 다시 작성해요."
        choices = ["다시 찍기"]
    elif fields:
        names = ", ".join(FIELD_LABELS[k] for k in fields)
        text += f" {names}{_object_particle(names)} 고친 뒤 [제출하기]로 내용을 확인하고 다시 제출해 주세요."
        text += " 어떻게 고칠지 말씀해 주셔도 돼요."
        choices = ["직접 수정"]
    else:
        text += (
            " 사유에 맞게 고친 뒤 [제출하기]로 내용을 확인하고 다시 제출해 주세요."
            " 어떻게 고칠지 말씀해 주셔도 돼요."
        )
        choices = ["직접 수정"]
    store.add_message(rid, "assistant", text, choices=choices)
    return _reply(text, _done(text, receipt, choices=choices))


def opening_text(receipt: dict[str, Any]) -> str:
    """First words once the receipt is read: only "check the result" (one thing at a time)."""
    text = "영수증을 읽었어요. 내용이 맞는지 확인해 주세요."
    unclear = [FIELD_LABELS[k] for k in receipt.get("needs_check", []) if k in FIELD_LABELS]
    if unclear:
        text += f" {', '.join(unclear)}은(는) 흐릿하게 읽혀서 사진과 꼭 비교해 주세요."
    if any(c["code"] == "amount_mismatch" for c in receipt.get("checks", [])):
        text += " 금액 검산이 맞지 않아 금액도 함께 봐 주세요."
    return text


def _warning_hint(receipt: dict[str, Any]) -> str:
    """Late-night / weekend / duplicate notes as one plain sentence ("" when there are none)."""
    codes = {c["code"] for c in receipt.get("checks", [])}
    at = parse_transaction_at((receipt.get("fields") or {}).get("transaction_at"))
    when = []
    if at and "weekend" in codes:
        when.append(f"{WEEKDAYS[at.weekday()]}요일")
    if at and "late_night" in codes:
        when.append(f"밤 {at.hour - 12}시" if at.hour >= 12 else f"새벽 {at.hour}시")
    hints = [f"{' '.join(when)} 결제라 사유를 목적에 함께 적어 두면 좋아요."] if when else []
    if codes & {"duplicate", "same_approval"}:
        hints.append("같은 증빙이 이미 있어요. 중복 제출이 아닌지 확인해 주세요.")
    return " ".join(hints)


def _held_suggestions(rid: str, receipt: dict[str, Any]) -> list[dict[str, str]]:
    """Suggestions made with the result but not shown yet (or the last ones shown)."""
    for m in reversed(store.list_messages(rid)):
        if m["role"] == "assistant" and (m.get("pending_suggestions") or m.get("suggestions")):
            held = m.get("pending_suggestions") or m["suggestions"]
            # Re-labelled: suggestions saved before the category revision carry old codes and labels.
            return suggestions((x.get("purpose"), x.get("category")) for x in held)
    return mock_suggestions(receipt)  # nothing prepared: examples from history and the category


def _card_turn(receipt: dict[str, Any], user: User, message: str) -> StreamingResponse:
    """[맞아요]/[직접 수정]/[수정 완료] on the result card: answered without the model.

    Confirming moves on to the next single question (purpose and category, with the held suggestions);
    "직접 수정" points to the form and waits for "수정 완료".
    """
    rid = receipt["id"]
    history = [m for m in store.list_messages(rid) if m["role"] == "assistant"]
    last = history[-1] if history else {}
    store.add_message(rid, "user", message)
    fields = receipt.get("fields", {})
    buttons: dict[str, Any] = {}
    actions: list[str] = []
    if message in EDIT_REPLIES:
        text = (
            "아래 증빙 정보에서 틀린 칸을 고친 뒤 [수정 완료]를 눌러 주세요. "
            "무엇이 틀렸는지 말씀해 주셔도 돼요."
        )
        buttons = {"choices": ["수정 완료"]}
    elif receipt["analysis_status"] != "done":
        text = "분석이 끝나면 결과를 보여 드릴게요."
    else:
        if not receipt.get("result_confirmed_at"):
            receipt = store.update_receipt(rid, result_confirmed_at=now_iso())
        text = "고친 내용으로 확인했어요." if message in EDITED_REPLIES else "확인했어요."
        hint = _warning_hint(receipt)
        if not fields.get("purpose"):
            text = " ".join(x for x in (text, hint, "어떤 일로 쓰신 비용인가요?") if x)
            buttons = {"suggestions": _held_suggestions(rid, receipt)}
        elif not fields.get("category"):
            text = " ".join(x for x in (text, hint, "지출 분류를 골라 주세요.") if x)
            buttons = {"choices": list(CATEGORIES.values())[:4]}
        else:
            step, actions = _next_step(receipt)
            text = " ".join(x for x in (text, hint, step) if x)
    store.add_message(
        rid, "assistant", text, slot=last.get("slot"), **buttons, **({"actions": actions} if actions else {})
    )
    done = _done(text, receipt, slot=last.get("slot"), actions=actions, changed=True, **buttons)
    return _reply(text, done)


@app.get("/chat/receipts/{receipt_id}/messages")
def messages(receipt_id: str, user: User = Depends(current_user)) -> dict[str, Any]:
    _load(receipt_id, user, owner_only=False)
    return {"items": [m for m in store.list_messages(receipt_id) if m["role"] in ("user", "assistant")]}


def _agent_turn(receipt: dict[str, Any], user: User, body: Turn) -> StreamingResponse:
    """AI assistant with tools (RF_AI_MODE=bedrock)."""
    rid = receipt["id"]
    if body.message and body.message.strip():
        store.add_message(rid, "user", body.message.strip())
        store.update_receipt(rid, timings={"chat_last_answer": now_iso()})
    elif body.event:
        history = store.list_messages(rid)
        if body.event == "start" and any(m["role"] == "assistant" for m in history):
            body.event = None  # reopening an existing conversation: nothing new to say
        elif body.event == "analysis_done" and (
            receipt.get("result_confirmed_at") or any(m.get("event") == "analysis_done" for m in history)
        ):
            body.event = None  # already announced, or the employee already confirmed the result
        if body.event:
            store.add_message(rid, "event", body.event, event=body.event)
    if not (body.message and body.message.strip()) and not body.event:
        return StreamingResponse(
            iter(
                [
                    _sse(
                        "done",
                        {
                            "text": "",
                            "choices": [],
                            "actions": [],
                            "changed": False,
                            "repeat": True,
                            "fields": receipt.get("fields", {}),
                        },
                    )
                ]
            ),
            media_type="text/event-stream",
        )
    history = store.list_messages(rid)
    first_reply = not any(m["role"] == "assistant" for m in history)
    # The result came in and nobody has confirmed it yet: ask only that (fixed words, shown at once).
    # The model still runs to prepare the purpose · category suggestions, held until the card is confirmed.
    opening = (
        body.event == "analysis_done"
        and receipt["analysis_status"] == "done"
        and not receipt.get("result_confirmed_at")
    )

    def stream() -> Iterator[str]:
        state, text = None, ""
        if opening:
            text = opening_text(receipt)
            yield _sse("delta", {"text": text})
        for kind, value in agent.run_turn(receipt, user, history):
            if opening and kind != "done":
                continue
            if kind == "delta":
                yield _sse("delta", {"text": value})
            elif kind == "tool":
                yield _sse("tool", value)
            else:
                state, said = value
                text = text if opening else said
        text = text or "확인했어요."
        if opening:
            buttons = {"pending_suggestions": state.suggestions}
            state.choices, state.suggestions = [], []
        else:
            buttons = {"choices": state.choices, "suggestions": state.suggestions, "actions": state.actions}
        store.add_message(rid, "assistant", text, **{k: v for k, v in buttons.items() if v})
        if first_reply:
            store.update_receipt(rid, timings={"chat_first_question": now_iso()})
        yield _sse(
            "done",
            {
                "text": text,
                "choices": state.choices,
                "suggestions": state.suggestions,
                "actions": state.actions,
                "changed": state.changed,
                "repeat": False,
                "slot": None,
                "finished": False,
                "fields": state.receipt.get("fields", {}),
            },
        )

    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


@app.post("/chat/receipts/{receipt_id}/turn")
def turn(receipt_id: str, body: Turn, user: User = Depends(employee_only)) -> StreamingResponse:
    receipt = _load(receipt_id, user, owner_only=True)
    if receipt["review_status"] not in EDITABLE_STATUSES:
        raise ApiError(409, "not_editable", "제출된 증빙은 대화로 수정할 수 없습니다.")
    if body.event == "changes_requested":
        return _changes_turn(receipt)
    if body.choice:
        return _choice_turn(receipt, user, body.choice)
    if body.message and body.message.strip() in CARD_REPLIES:
        return _card_turn(receipt, user, body.message.strip())
    if get_settings().ai_mode == "bedrock":
        return _agent_turn(receipt, user, body)
    # Mock mode: the scripted dialog (fixed questions), used by tests.
    history = [m for m in store.list_messages(receipt_id) if m["role"] in ("user", "assistant")]
    pending = next((m.get("slot") for m in reversed(history) if m["role"] == "assistant"), None)

    if body.message and body.message.strip():
        store.add_message(receipt_id, "user", body.message.strip())
        try:
            parsed = parse_answer(body.message, pending)
        except ModelError:
            log.exception("answer parsing failed")
            parsed = Parsed()
        # Never overwrite something already filled unless it is the slot we just asked about.
        current = receipt.get("fields", {})
        values = {
            k: v
            for k, v in normalize_fields(parsed.values).items()
            if v and (k == pending or not current.get(k))
        }
        ai_filled = set(receipt.get("ai_filled", []))
        ai_filled |= {k for k in values if k in parsed.ai_keys}
        ai_filled -= {k for k in values if k not in parsed.ai_keys} | parsed.confirmed
        receipt = store.apply_fields(
            receipt, values, ai_filled=sorted(ai_filled), timings={"chat_last_answer": now_iso()}
        )
        history = [m for m in store.list_messages(receipt_id) if m["role"] in ("user", "assistant")]

    reply = next_reply(receipt, history)
    last = history[-1] if history else None
    repeat = (
        last and last["role"] == "assistant" and last.get("slot") == reply.slot and last["text"] == reply.text
    )
    if not repeat:
        ready = reply.finished and receipt["analysis_status"] == "done"
        buttons = {
            "choices": reply.choices,
            "suggestions": reply.suggestions,
            "actions": ["submit"] if ready else [],
        }
        store.add_message(
            receipt_id, "assistant", reply.text, slot=reply.slot, **{k: v for k, v in buttons.items() if v}
        )
        if not any(m["role"] == "assistant" for m in history):
            store.update_receipt(receipt_id, timings={"chat_first_question": now_iso()})

    def stream() -> Iterator[str]:
        for piece in _chunks(reply.text):
            yield _sse("delta", {"text": piece})
        yield _sse(
            "done",
            {
                "text": reply.text,
                "slot": reply.slot,
                "choices": reply.choices,
                "suggestions": reply.suggestions,
                "finished": reply.finished,
                "repeat": bool(repeat),
                "actions": ["submit"] if reply.finished and receipt["analysis_status"] == "done" else [],
                "changed": bool(body.message and body.message.strip()),
                "fields": receipt.get("fields", {}),
            },
        )

    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})
