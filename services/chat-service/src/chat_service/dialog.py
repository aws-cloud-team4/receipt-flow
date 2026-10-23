"""Slot-filling dialog: which question comes next and how a free-text answer maps to fields.

Questions are fixed templates (fast, predictable); the model is only used to structure answers.
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from receiptflow_common import store
from receiptflow_common.bedrock import call_tool
from receiptflow_common.config import get_settings
from receiptflow_common.domain import CATEGORIES, CATEGORY_HINTS, FIELD_LABELS, ro, to_category

MAX_QUESTIONS = 3
# Department comes from the login profile, so the chat never asks for it.
SLOTS = ("purpose", "category")
ANSWER_SLOTS = SLOTS
YES = re.compile(r"^(네|넵|예|응|맞아요?|맞습니다|맞음|ㅇㅇ|그래요?)[.!]?$")

QUESTIONS = {
    "purpose": "지출 목적과 분류를 알려 주세요. 추천을 누르거나 직접 적어 주세요.",
    "category": "지출 분류를 골라 주세요.",
}
DEFAULT_SUGGESTIONS = [
    ("팀 회의 다과", "food"),
    ("야근 식사", "food"),
    ("고객사 미팅 식사", "entertainment"),
    ("외근 교통비", "travel"),
    ("사무용품 구매", "supplies"),
    ("서류 택배 발송", "delivery"),
]
MAX_SUGGESTIONS = 3

PARSE_SYSTEM = """직원이 업무 지출에 대해 한 답변을 증빙 항목으로 정리합니다.
- purpose: 지출 목적을 짧은 명사구로 (예: '고객사 미팅 점심')
- category: 답변 내용으로 판단한 지출 분류 코드. 판단이 어려우면 null
답변에 명시되지 않은 항목은 반드시 null로 둡니다.
지출 분류 코드:
""" + "\n".join(f"- {code}: {CATEGORIES[code]} ({hint})" for code, hint in CATEGORY_HINTS.items())

PARSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "purpose": {"type": ["string", "null"]},
        "category": {"type": ["string", "null"], "enum": [*CATEGORIES, None]},
    },
    "required": ["purpose", "category"],
}


@dataclass
class Parsed:
    values: dict[str, Any] = field(default_factory=dict)
    ai_keys: set[str] = field(default_factory=set)  # values the model inferred (not typed or picked)
    confirmed: set[str] = field(default_factory=set)  # suggestions the person accepted as they are


@dataclass
class Reply:
    text: str
    slot: str | None = None  # what the next user answer is expected to fill
    choices: list[str] = field(default_factory=list)
    suggestions: list[dict[str, str]] = field(default_factory=list)
    finished: bool = False


def suggestions(pairs: Iterable[tuple[Any, Any]]) -> list[dict[str, str]]:
    """(purpose, category) pairs → buttons: valid category, short purpose, no repeats, at most 3."""
    out: list[dict[str, str]] = []
    for purpose, category in pairs:
        code = to_category(category) if isinstance(category, str) else None
        text = purpose.strip()[:40] if isinstance(purpose, str) else ""
        if code and text and all(s["purpose"] != text for s in out):
            out.append({"purpose": text, "category": code, "category_label": CATEGORIES[code]})
    return out[:MAX_SUGGESTIONS]


def parse_answer(message: str, pending: str | None) -> Parsed:
    text = message.strip()
    if not text:
        return Parsed()
    if pending == "category":
        code = to_category(text)
        if code:
            return Parsed({"category": code}, confirmed={"category"})
        if YES.match(text):
            return Parsed(confirmed={"category"})  # keeps the suggested category
    mock = get_settings().ai_mode == "mock"
    short = pending == "purpose" and len(text) <= 20 and "," not in text
    if mock or short:
        # Short direct answers ("팀 점심") need no model call; they are the person's own words.
        return Parsed({pending: text}) if pending == "purpose" else Parsed()
    question = QUESTIONS.get(pending or "", "")
    parsed, _ = call_tool(
        PARSE_SYSTEM,
        [{"text": f"질문: {question}\n답변: {text}"}],
        "record_answer",
        "답변에서 읽은 증빙 항목을 기록한다",
        PARSE_SCHEMA,
        model=get_settings().chat_model,
        max_tokens=300,
    )
    out = {k: v.strip() for k, v in parsed.items() if isinstance(v, str) and v.strip()}
    if "category" in out and not to_category(out["category"]):
        del out["category"]
    return Parsed(out, ai_keys=set(out))


def mock_suggestions(receipt: dict[str, Any]) -> list[dict[str, str]]:
    """Without a model: the employee's earlier purposes, then examples that fit the suggested category."""
    past = [
        (f.get("purpose"), f.get("category"))
        for r in store.list_by_owner(receipt["owner_sub"])[:20]
        if r["id"] != receipt["id"] and (f := r.get("fields", {}))
    ]
    guess = receipt.get("fields", {}).get("category")
    defaults = sorted(DEFAULT_SUGGESTIONS, key=lambda pair: pair[1] != guess)
    return suggestions([*past, *defaults])


def _category_reply(fields: dict[str, Any]) -> Reply:
    labels = list(CATEGORIES.values())
    current = CATEGORIES.get(fields.get("category") or "")
    if current:
        others = [label for label in labels if label != current]
        return Reply(
            f"지출 분류를 '{current}'{ro(current)} 넣었어요. "
            "맞으면 눌러 주시고, 아니면 다른 분류를 골라 주세요.",
            "category",
            [current, *others],
        )
    return Reply(QUESTIONS["category"], "category", labels)


def next_reply(receipt: dict[str, Any], messages: list[dict[str, Any]]) -> Reply:
    fields = receipt.get("fields", {})
    asked = [m.get("slot") for m in messages if m["role"] == "assistant"]
    question_count = sum(1 for s in asked if s in SLOTS)

    for slot in SLOTS:
        if question_count >= MAX_QUESTIONS:
            break
        if slot == "category":
            # Ask once even when a category is already suggested, so a person confirms it.
            if "category" not in asked or not fields.get("category"):
                return _category_reply(fields)
            continue
        if fields.get(slot):
            continue
        if slot in asked:
            text = f"{FIELD_LABELS[slot]}을(를) 한 번만 더 알려 주세요. 짧게 적어 주셔도 됩니다."
        elif question_count == 0:
            text = "분석하는 동안 몇 가지만 여쭤볼게요. " + QUESTIONS[slot]
        else:
            text = QUESTIONS[slot]
        return Reply(text, slot, suggestions=mock_suggestions(receipt))

    status = receipt.get("analysis_status")
    if status in ("waiting", "queued", "processing"):
        return Reply("감사합니다. 영수증 분석이 끝나면 확인할 내용을 알려 드릴게요.", "wait_analysis")
    if status == "failed":
        return Reply(
            "영수증을 읽지 못했어요. 다시 찍어 올리거나 확인 화면에서 직접 입력해 주세요.", finished=True
        )

    if "confirm" not in asked:
        issues = [c["message"] for c in receipt.get("checks", []) if c["code"] == "amount_mismatch"]
        unclear = receipt.get("needs_check", [])
        if unclear:
            issues.append(f"{', '.join(FIELD_LABELS[k] for k in unclear)} 값을 정확히 읽지 못했어요.")
        if issues:
            return Reply(
                " ".join(issues) + " 확인 화면에서 사진과 비교해 고쳐 주시겠어요?",
                "confirm",
                ["직접 수정", "값이 맞아요"],
            )

    return Reply("필요한 정보가 모두 모였어요. 확인 화면에서 내용을 살펴보고 제출해 주세요.", finished=True)
