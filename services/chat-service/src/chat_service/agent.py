"""AI assistant that works on one receipt with tools (Bedrock ConverseStream).

Each turn the model sees the receipt as it is right now (fields, checks, analysis state, item
summary, similar past receipts) and may call tools to change it. The person always submits.
Used when RF_AI_MODE=bedrock; tests and mock mode use the scripted dialog in dialog.py.
"""

import json
import logging
import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

from botocore.exceptions import ClientError
from receiptflow_common import aws, store
from receiptflow_common.auth import User
from receiptflow_common.config import get_settings
from receiptflow_common.domain import (
    AI_FIELDS,
    CATEGORIES,
    CATEGORY_HINTS,
    FIELD_LABELS,
    PROFILE_FIELDS,
    missing_required,
    normalize_fields,
    now_iso,
    parse_transaction_at,
    ro,
    to_category,
)

from .dialog import suggestions

log = logging.getLogger("chat-service.agent")

MAX_ROUNDS = 4  # model calls per turn (tool use → result → …)
HISTORY_LIMIT = 24
EDITABLE_BY_AI = (*AI_FIELDS, "purpose")
ACTOR = "AI 어시스턴트"
BUTTON_TOOLS = ("show_choices", "suggest_expense")  # only put buttons on the screen
CLAIMS_CHANGE = re.compile("(바꿨|고쳤|수정했|저장했|반영했|넣었|정했)")
NUDGE_CLAIM = (
    "[시스템 점검] 이번 턴에 증빙을 바꾸는 도구를 호출하지 않았는데 바꿨다고 답했습니다. "
    "실제로 바꿔야 하면 지금 도구를 호출하고, 아니면 바꿨다는 말 없이 다시 답하세요."
)
NUDGE_VOICE = (
    "[시스템 점검] 방금 답은 한국어가 아니거나 생각 과정('사용자가 …', '…하겠다')이 섞였습니다. "
    "도구는 다시 부르지 말고, 직원에게 할 말만 한국어 존댓말 2문장 이내로 다시 쓰세요."
)
VOICE_CHECK_CHARS = 12  # letters seen before streaming starts
SAFE_ASK = "지출 목적과 분류를 알려 주세요."
SAFE_REPLY = "확인했어요. 더 필요한 게 있으면 말씀해 주세요."
THIRD_PERSON = re.compile(
    r"(사용자[가는의를]|I'll|I will|Let me|붙이겠|붙여 두|붙였|붙입니다)"
)  # notes, not a reply


def _voice_ok(text: str) -> bool:
    """Korean, addressed to the employee: not English reasoning or notes about "the user"."""
    hangul = sum("가" <= c <= "힣" for c in text)
    latin = sum(c.isascii() and c.isalpha() for c in text)
    return hangul >= latin and not THIRD_PERSON.search(text)


def _nudge(text: str, changed: bool) -> str | None:
    if text and not _voice_ok(text):
        return NUDGE_VOICE
    if not changed and CLAIMS_CHANGE.search(text):
        return NUDGE_CLAIM
    return None


SYSTEM = """당신은 receiptflow의 AI 어시스턴트입니다.
직원이 업무 지출 영수증 증빙 한 건을 완성하도록 돕습니다.

반드시 한국어로만 답합니다. 생각·판단 과정·계획("~하겠다", "I'll")은 쓰지 않고, 직원에게 할 말만 씁니다.
직원을 "사용자"라고 3인칭으로 부르지 않습니다. 화면에 그대로 보이는 말입니다.

말투: 한국어, 존댓말, 최대 2문장. 이모지와 목록 기호는 쓰지 않습니다.
- 필요한 도구를 먼저 모두 호출하고, 사용자에게 하는 말은 맨 마지막에 한 번만 씁니다.
- 이미 말한 내용, 화면에 보이는 값은 되풀이하지 않습니다. 바뀐 것과 다음에 할 일만 말합니다.

원칙
- [현재 증빙]이 최신 사실입니다. 거기 없는 값을 지어내지 않습니다.
- 사용자가 직접 말한 값만 update_fields로 고칩니다.
  추천은 "~로 할까요?"처럼 묻고, 동의하면 반영합니다.
- 지출 분류는 set_category로 정합니다.
  사용자가 고르거나 동의했으면 confirmed_by_user=true, 당신의 추천이면 false.
  이미 같은 분류로 정해져 있으면 다시 호출하지 않습니다.
- 분류 원칙 (직원 증빙 제출용, 회계 계정은 회사가 따로 연결):
  식사·회식·회의 다과·탕비실 간식은 모두 식사·간식비(food)이고, 어떤 식사인지는 지출 목적에 적습니다.
  고객·거래처 등 외부 사람과의 식사·외부 선물·경조 화환은 접대·선물비(entertainment).
  영수증만으로 정하지 말고 직원이 말했을 때만, 그때 상대 거래처를 목적에 함께 적도록 묻습니다.
  직원이 거래처 이름을 밝히지 않겠다고 하면 그대로 두되,
  "거래처 이름이 없으면 검수 담당자가 보완 요청을 보낼 수 있어요."라고 한 번만 알려 줍니다.
  임직원 복지 목적의 선물·경조, 워크숍·사내 행사는 행사·복리후생비(welfare_event).
  행사에서 따로 결제한 식사는 food로 하고 목적에 행사명을 적습니다.
  교통·출장비(travel), 사무용품·소모품비(supplies)는 세부 항목(주유·주차·숙박·정비, 사무기기·가구 등)이
  목적에 드러나게 합니다. 기타 업무비(other)는 구체적인 사용 목적을 꼭 받습니다.
- 작성자 부서에 맞춰 추천 순서를 정합니다 (예시일 뿐, 단정하지 않음):
  영업: 거래처 미팅·외근 교통·샘플 발송 / 인사: 면접·교육·워크숍·경조 / 개발: 도서·세미나·클라우드·구독
  마케팅·홍보: 광고·홍보물·전시 / 총무·경영지원: 비품·소모품·수리·탕비실 간식
- 가게 종류·품목별 목적·분류 예:
  식당·카페·편의점: 팀 점심 식사·식사·간식비 / 회의 다과·식사·간식비 / 거래처 미팅 식사·접대·선물비
  주유·충전·주차·통행료·택시: 외근 차량 주유·교통·출장비 / 고객사 방문 택시·교통·출장비
  철도·항공·숙박: 부산 출장 KTX·교통·출장비 / 출장 숙박·교통·출장비
  문구·다이소·약국·전자제품: 사무용품 구매·사무용품·소모품비 / 사무실 상비약·사무용품·소모품비
  택배·우편·퀵: 계약서 등기 발송·우편·배송비 / 샘플 택배 발송·우편·배송비
  도서·강의·세미나: 업무 도서 구매·도서·교육비 / 직무 교육 수강료·도서·교육비
  꽃집·선물: 거래처 개업 화환·접대·선물비 / 임직원 경조 화환·행사·복리후생비
  클라우드·소프트웨어·통신: 클라우드 사용료·통신·구독비 / 업무용 툴 구독·통신·구독비
  인쇄·광고: 홍보물 인쇄·광고·홍보비 / 온라인 광고 집행·광고·홍보비
- 마트 생활용품처럼 개인 용도와 헷갈리는 구매는 단정하지 말고 업무 용도를 확인합니다.
- 주말·심야 거래 경고가 있으면 사유(예: 주말 행사 지원)를 목적에 함께 적도록 권합니다.
- 선택 항목(카드사·카드번호·승인번호·사업자번호·공급가액·부가세·면세금액)은 비어 있어도 묻지 않습니다.
- 지출 목적이나 분류가 비어 있으면 "지출 목적과 분류를 알려 주세요."처럼 함께 묻고(분석 중에도),
  suggest_expense로 목적·분류 쌍 추천을 2~3개 붙입니다.
  추천 근거: 품목 요약, 가게 종류, [현재 증빙]의 거래 시간대(서버가 계산한 값, 직접 시각을 해석하지 않음),
  같은 가게 과거 증빙(있으면 맨 앞), 작성자 부서.
  목적은 "팀 분기 마감 점심 회식"처럼 짧은 명사구, 사실처럼 단정하지 않습니다.
  추천은 거래 시간대와 맞아야 합니다: 야근·심야 목적은 시간대가 저녁(19시 이후)·밤·새벽일 때만,
  점심이면 점심 식사·회의 다과·업무 중 간식처럼 낮에 맞는 목적을 추천합니다.
  추천 내용은 버튼에 보이므로 말로 다시 나열하지 않고, 버튼을 붙인다고도 말하지 않습니다.
- 직원이 무슨 지출인지 말하면(짧아도) 그 말을 목적 명사구로 정리해 update_fields로 바로 넣습니다.
  (예: "팀원들이랑 점심 먹었어" → "팀 점심 식사"). 이때는 suggest_expense를 다시 붙이지 않습니다.
  분류가 비어 있으면 set_category(confirmed_by_user=false)로 추천을 넣고 "식사·간식비로 할까요?"처럼 물은 뒤
  show_choices로 ["예", "아니요"]를 붙입니다.
- [화면 이벤트] 분석 완료: 결과 확인은 화면이 먼저 따로 묻습니다 (당신의 이번 답은 화면에 보이지 않음).
  지출 목적이나 분류가 비어 있으면 suggest_expense만 호출하고,
  답은 "추천을 준비했습니다." 한 문장으로 끝냅니다.
  주의 경고(심야·주말 등)가 있으면 추천 목적에 그 사유가 드러나게 합니다 (예: 야근 중 식사).
- 목적을 물을 때는 "비어 있습니다"라고 하지 말고 "어떤 일로 쓰신 비용인가요?"처럼 묻습니다.
- [빠진 필수 항목]이 비어 있지 않으면 "준비됐다", "제출하기를 눌러 주세요"라고 말하지 않습니다.
- 결과 카드에 대해 직원이 "맞아요"라고 하면 confirm_result를 호출합니다.
  다른 질문에 대한 "예"·"네"는 결과 확인이 아니므로 confirm_result를 부르지 않습니다.
  ([현재 증빙]의 결과 확인함이 false일 때만)
  "직접 수정"이라고 하면 무엇이 틀렸는지 말해 달라고 하거나, 아래 폼에서 고쳐도 된다고 안내합니다.
- 점검 경고(금액 불일치, 중복·같은 승인번호, 심야·주말 등)는 왜 떴는지 쉽게 설명합니다.
- 목적·분류가 채워지고 분석이 끝났으면 check_submission을 호출합니다.
  준비됐으면 "제출할 내용을 확인해 주세요."라고만 안내합니다 (화면에 최종 확인 카드가 뜸).
  빠진 게 있으면 그것만 묻습니다.
  unconfirmed에 지출 분류가 있으면 AI가 넣은 분류를 직원이 아직 확인하지 않은 것이므로
  "식사·간식비로 할까요?"처럼 지금 분류를 묻고 show_choices로 ["예", "아니요"]를 붙입니다.
  직원이 동의하면 set_category(confirmed_by_user=true)를 부른 뒤 다시 check_submission을 호출합니다.
  당신은 제출하지 않으며 제출했다고 말하지 않습니다.
- 예/아니요로 답할 수 있는 질문(예: "식사·간식비로 할까요?")에는 show_choices로 ["예", "아니요"]를 붙입니다.
  직원이 "예"라고 하면 직전에 당신이 예/아니요로 물은 것에만 동의한 것입니다.
  그런 질문이 없었는데 "예"라고 하면 무엇을 원하는지 짧게 되묻습니다. 추천 중 하나를 마음대로 고르지 않습니다.
  "아니요"면 다른 분류 후보를 show_choices로 붙입니다.
- 그 밖에 고를 것이 있으면 show_choices로 버튼을 최대 3개 붙입니다 (예: 분류 후보).
  목적·분류 추천은 show_choices가 아니라 suggest_expense로 합니다.
  결과 카드에는 맞아요/직접 수정 버튼이 이미 있으니 그 버튼은 만들지 않습니다.
- 도구 결과의 before와 after가 다르면 "바꿨다"고 말합니다. 이미 그 값이었다고 하지 않습니다.
- 부서·직급·이름·직원코드는 프로필 값이라 바꿀 수 없다고 안내합니다.
- 증빙과 관계없는 요청은 한 문장으로 정중히 거절하고 하던 일로 돌아갑니다."""

TOOLS: list[dict[str, Any]] = [
    {
        "name": "update_fields",
        "description": (
            "사용자가 직접 말한 값으로 증빙 칸을 고친다. 금액은 원 단위 정수, 일시는 YYYY-MM-DDTHH:MM."
        ),
        "schema": {
            "type": "object",
            "properties": {
                "fields": {
                    "type": "object",
                    "description": "바꿀 칸만. 키: "
                    + ", ".join(f"{k}({FIELD_LABELS[k]})" for k in EDITABLE_BY_AI),
                    "properties": {k: {"type": ["string", "integer", "null"]} for k in EDITABLE_BY_AI},
                }
            },
            "required": ["fields"],
        },
    },
    {
        "name": "set_category",
        "description": "지출 분류를 정한다.",
        "schema": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "enum": list(CATEGORIES)},
                "confirmed_by_user": {"type": "boolean", "description": "사용자가 고르거나 동의했으면 true"},
            },
            "required": ["code", "confirmed_by_user"],
        },
    },
    {
        "name": "confirm_result",
        "description": "사용자가 AI가 읽은 영수증 결과가 맞다고 확인했을 때 호출한다.",
        "schema": {"type": "object", "properties": {}},
    },
    {
        "name": "show_choices",
        "description": "다음 답에 쓸 버튼을 화면에 붙인다 (최대 8개, 짧게).",
        "schema": {
            "type": "object",
            "properties": {"options": {"type": "array", "items": {"type": "string"}, "maxItems": 8}},
            "required": ["options"],
        },
    },
    {
        "name": "suggest_expense",
        "description": (
            "지출 목적·분류가 비어 있을 때 영수증 맥락으로 고른 목적·분류 쌍 추천을 화면 버튼으로 붙인다. "
            "사용자가 누르면 그대로 저장된다."
        ),
        "schema": {
            "type": "object",
            "properties": {
                "suggestions": {
                    "type": "array",
                    "maxItems": 3,
                    "items": {
                        "type": "object",
                        "properties": {
                            "purpose": {"type": "string", "description": "짧은 명사구"},
                            "category": {"type": "string", "enum": list(CATEGORIES)},
                        },
                        "required": ["purpose", "category"],
                    },
                }
            },
            "required": ["suggestions"],
        },
    },
    {
        "name": "check_submission",
        "description": "제출해도 되는지 점검한다. 준비됐으면 화면에 제출 버튼이 나타난다.",
        "schema": {"type": "object", "properties": {}},
    },
]

EVENTS = {
    "start": "[화면 이벤트] 직원이 증빙 작성을 시작했습니다. 영수증 분석이 진행 중일 수 있습니다.",
    "analysis_done": "[화면 이벤트] 영수증 분석이 끝났습니다. 결과 카드가 화면에 표시되었습니다.",
}


@dataclass
class TurnState:
    receipt: dict[str, Any]
    user: User
    choices: list[str] = field(default_factory=list)
    suggestions: list[dict[str, str]] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)
    changed: bool = False


# ── context ──────────────────────────────────────────────────────────────────


def _similar(receipt: dict[str, Any]) -> list[dict[str, Any]]:
    f = receipt.get("fields", {})
    biz = re.sub(r"\D", "", f.get("business_number") or "")
    name = re.sub(r"\s+", "", f.get("merchant_name") or "")
    if not (biz or name):
        return []
    out = []
    for r in store.list_by_owner(receipt["owner_sub"]):
        if r["id"] == receipt["id"]:
            continue
        rf = r.get("fields", {})
        same_biz = biz and re.sub(r"\D", "", rf.get("business_number") or "") == biz
        same_name = name and re.sub(r"\s+", "", rf.get("merchant_name") or "") == name
        if (same_biz or same_name) and (rf.get("purpose") or rf.get("category")):
            out.append(
                {
                    "거래일": (rf.get("transaction_at") or "")[:10],
                    "분류": CATEGORIES.get(rf.get("category") or "", None),
                    "목적": rf.get("purpose"),
                    "총액": rf.get("total_amount"),
                }
            )
        if len(out) == 3:
            break
    return out


# (first hour, name): the band a transaction falls in, so the model doesn't read the clock itself
_BANDS = ((0, "새벽"), (6, "아침"), (11, "점심"), (14, "오후"), (18, "저녁"), (21, "밤"))


def time_of_day(transaction_at: str | None) -> str | None:
    """'2026-10-14T12:57' → '점심 (12시 57분)'; None when the time is unknown."""
    at = parse_transaction_at(transaction_at)
    if at is None:
        return None
    band = [name for start, name in _BANDS if at.hour >= start][-1]
    return f"{band} ({at.hour}시 {at.minute}분)"


def context(receipt: dict[str, Any], user: User) -> str:
    f = receipt.get("fields", {})
    status = {
        "waiting": "사진 대기",
        "queued": "분석 대기",
        "processing": "분석 중",
        "done": "분석 완료",
        "failed": "분석 실패",
    }[receipt["analysis_status"]]
    state = {
        "분석 상태": status,
        "분석 실패 사유": receipt.get("analysis_error"),
        "필드": {FIELD_LABELS[k]: f.get(k) for k in (*AI_FIELDS, "purpose", *PROFILE_FIELDS)},
        "거래 시간대": time_of_day(f.get("transaction_at")),
        "지출 분류": CATEGORIES.get(f.get("category") or "", None),
        "AI가 채운 칸(사람이 아직 확인 안 함)": [FIELD_LABELS[k] for k in receipt.get("ai_filled", [])],
        "확인 필요(흐리거나 못 읽음)": [FIELD_LABELS[k] for k in receipt.get("needs_check", [])],
        "점검 결과": [c["message"] for c in receipt.get("checks", [])],
        "빠진 필수 항목": [FIELD_LABELS[k] for k in missing_required(f)],
        "결과 확인함": bool(receipt.get("result_confirmed_at")),
        "품목 요약": (receipt.get("ai_context") or {}).get("items"),
        "같은 가게 과거 증빙": _similar(receipt),
    }
    if receipt.get("review_status") == "changes_requested":  # the reviewer sent it back
        state["담당자 보완 요청"] = {
            "사유": receipt.get("review_note"),
            "다시 볼 칸": [FIELD_LABELS.get(k, "사진") for k in receipt.get("review_fields") or []],
        }
    profile = {"이름": user.name, "부서": user.department, "직급": user.position}
    categories = "\n".join(f"- {code}: {CATEGORIES[code]} ({hint})" for code, hint in CATEGORY_HINTS.items())
    return (
        f"[현재 증빙]\n{json.dumps(state, ensure_ascii=False, indent=1)}\n\n"
        f"[작성자]\n{json.dumps(profile, ensure_ascii=False)}\n\n[지출 분류 코드]\n{categories}"
    )


def history_messages(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Stored chat (user / assistant / event) → Converse messages: alternating, starting with user."""
    msgs: list[dict[str, Any]] = []
    for m in history[-HISTORY_LIMIT:]:
        if not (m.get("text") or "").strip():
            continue  # Converse rejects empty text blocks
        role = "assistant" if m["role"] == "assistant" else "user"
        text = EVENTS.get(m.get("event") or "", m["text"]) if m["role"] == "event" else m["text"]
        if msgs and msgs[-1]["role"] == role:
            msgs[-1]["content"][0]["text"] += "\n" + text
        else:
            msgs.append({"role": role, "content": [{"text": text}]})
    if msgs and msgs[0]["role"] == "assistant":
        msgs.insert(0, {"role": "user", "content": [{"text": EVENTS["start"]}]})
    return msgs


# ── tools ────────────────────────────────────────────────────────────────────


def _label(values: dict[str, Any]) -> str:
    return ", ".join(f"{FIELD_LABELS[k]} {v if v is not None else '(비움)'}" for k, v in values.items())


def run_tool(name: str, args: dict[str, Any], st: TurnState) -> tuple[dict[str, Any], str | None]:
    """Execute one tool. Returns (result for the model, short summary for the screen)."""
    r = st.receipt
    if name == "update_fields":
        raw = args.get("fields") or {}
        blocked = sorted(set(raw) - set(EDITABLE_BY_AI))
        values = normalize_fields({k: v for k, v in raw.items() if k in EDITABLE_BY_AI})
        if not values:
            error = f"고칠 수 없는 칸입니다: {blocked}" if blocked else "바꿀 값이 없습니다."
            return {"ok": False, "error": error}, None
        before = r.get("fields") or {}
        values = {k: v for k, v in values.items() if before.get(k) != v}
        if not values:  # already so: nothing to change and nothing to show
            return {"ok": True, "unchanged": True}, None
        st.receipt = store.apply_fields(
            r,
            values,
            needs_check=[k for k in r.get("needs_check", []) if k not in values],
            ai_filled=[k for k in r.get("ai_filled", []) if k not in values],  # the person said these
        )
        store.add_event(r["id"], ACTOR, "ai_edited", f"{_label(values)} (사용자 요청)")
        st.changed = True
        result = {
            "ok": True,
            "updated": {FIELD_LABELS[k]: {"before": before.get(k), "after": v} for k, v in values.items()},
            "checks": [c["message"] for c in st.receipt.get("checks", [])],
        }
        if blocked:
            result["not_changed"] = blocked
        label = _label(values)
        return result, f"{label}{ro(label)} 고쳤어요"
    if name == "set_category":
        code = to_category(args.get("code"))
        if not code:
            return {"ok": False, "error": "알 수 없는 분류 코드"}, None
        by_user = bool(args.get("confirmed_by_user"))
        ai = set(r.get("ai_filled", []))
        before = r.get("fields", {}).get("category")
        if before == code and (by_user or "category" in ai) and not (by_user and "category" in ai):
            return {"ok": True, "category": CATEGORIES[code], "unchanged": True}, None
        ai = ai - {"category"} if by_user else ai | {"category"}
        st.receipt = store.apply_fields(r, {"category": code}, ai_filled=sorted(ai))
        if before != code:
            note = f"지출 분류 {CATEGORIES[code]}" + (" (사용자 선택)" if by_user else " (AI 추천)")
            store.add_event(r["id"], ACTOR, "ai_edited", note)
        st.changed = True
        label = CATEGORIES[code]
        # a suggestion is asked about in the reply ("…로 할까요?"), so only a decision gets a line
        return {
            "ok": True,
            "category": label,
        }, f"지출 분류를 {label}{ro(label)} 정했어요" if by_user else None
    if name == "confirm_result":
        st.receipt = store.update_receipt(r["id"], result_confirmed_at=now_iso())
        st.changed = True
        return {"ok": True}, "읽은 결과를 확인했어요"
    if name == "show_choices":
        st.choices = [str(o)[:30] for o in (args.get("options") or [])][:8]
        return {"ok": True}, None
    if name == "suggest_expense":
        picks = [x for x in args.get("suggestions") or [] if isinstance(x, dict)]
        st.suggestions = suggestions((x.get("purpose"), x.get("category")) for x in picks)
        return {"ok": True, "shown": len(st.suggestions)}, None
    if name == "check_submission":
        f = r.get("fields", {})
        pending = r["analysis_status"] in ("waiting", "queued", "processing")
        missing = [FIELD_LABELS[k] for k in missing_required(f)]
        errors = [c["message"] for c in r.get("checks", []) if c["level"] == "error"]
        warnings = [c["message"] for c in r.get("checks", []) if c["level"] == "warn"]
        # a category the AI put in (at analysis or as a suggestion) needs the person's yes first
        unconfirmed = (
            [FIELD_LABELS["category"]] if f.get("category") and "category" in r.get("ai_filled", []) else []
        )
        ready = not pending and not missing and not errors and not unconfirmed
        if ready and "submit" not in st.actions:
            st.actions.append("submit")
        return {
            "ready": ready,
            "analysis_pending": pending,
            "missing": missing,
            "unconfirmed": unconfirmed,
            "errors": errors,
            "warnings": warnings,
        }, None
    return {"ok": False, "error": f"없는 도구: {name}"}, None


# ── model loop ───────────────────────────────────────────────────────────────


def _tool_config() -> dict[str, Any]:
    return {
        "tools": [
            {
                "toolSpec": {
                    "name": t["name"],
                    "description": t["description"],
                    "inputSchema": {"json": t["schema"]},
                }
            }
            for t in TOOLS
        ]
    }


def _model_options(model: str) -> dict[str, Any]:
    """Haiku 5.5 thinks by default; for short tool-driven turns that only adds latency (~2x)."""
    if "haiku-5" in model:
        return {"additionalModelRequestFields": {"thinking": {"type": "disabled"}}}
    return {}


def _stream(messages: list[dict[str, Any]], system: str) -> Iterator[tuple[str, Any]]:
    """One ConverseStream call → ("text", str) deltas, then ("message", content blocks, stop reason)."""
    s = get_settings()
    resp = aws.client("bedrock-runtime").converse_stream(
        modelId=s.chat_model,
        system=[{"text": SYSTEM}, {"text": system}],
        messages=messages,
        inferenceConfig={"maxTokens": 800},
        toolConfig=_tool_config(),
        **_model_options(s.chat_model),
    )
    blocks: dict[int, dict[str, Any]] = {}
    stop = None
    for ev in resp["stream"]:
        if "contentBlockStart" in ev:
            start = ev["contentBlockStart"]
            if "toolUse" in start["start"]:
                tu = start["start"]["toolUse"]
                tool = {"toolUseId": tu["toolUseId"], "name": tu["name"]}
                blocks[start["contentBlockIndex"]] = {"tool": tool, "input": ""}
        elif "contentBlockDelta" in ev:
            i, d = ev["contentBlockDelta"]["contentBlockIndex"], ev["contentBlockDelta"]["delta"]
            if "text" in d:
                blocks.setdefault(i, {"text": ""})["text"] += d["text"]
                yield "text", d["text"]
            elif "toolUse" in d:
                blocks.setdefault(i, {"tool": {}, "input": ""})["input"] += d["toolUse"].get("input", "")
            elif "reasoningContent" in d:
                rc = blocks.setdefault(i, {"reasoning": {"text": "", "signature": None}})["reasoning"]
                rc["text"] += d["reasoningContent"].get("text", "")
                rc["signature"] = d["reasoningContent"].get("signature") or rc["signature"]
        elif "messageStop" in ev:
            stop = ev["messageStop"].get("stopReason")
    content = []
    for i in sorted(blocks):
        b = blocks[i]
        if "reasoning" in b:  # thinking blocks go back unchanged within the same turn
            rt = {"text": b["reasoning"]["text"]}
            if b["reasoning"]["signature"]:
                rt["signature"] = b["reasoning"]["signature"]
            content.append({"reasoningContent": {"reasoningText": rt}})
        elif "tool" in b:
            try:
                args = json.loads(b["input"] or "{}")
            except json.JSONDecodeError:
                args = {}
            content.append({"toolUse": {**b["tool"], "input": args}})
        elif b.get("text"):
            content.append({"text": b["text"]})
    yield "message", (content, stop)


def run_turn(receipt: dict[str, Any], user: User, history: list[dict[str, Any]]) -> Iterator[tuple[str, Any]]:
    """Yields ("delta", text), ("tool", {name, summary}) and finally ("done", TurnState, full_text)."""
    st = TurnState(receipt=receipt, user=user)
    messages = history_messages(history)
    texts: list[str] = []
    nudged = False
    try:
        for _ in range(MAX_ROUNDS):
            content, stop = [], None
            # Hold the words back until the start shows they are Korean and meant for the employee,
            # so English or "the user …" notes never flash on screen before the retry replaces them.
            held, live = "", False
            for kind, value in _stream(messages, context(st.receipt, user)):
                if kind != "text":
                    content, stop = value
                elif live:
                    yield "delta", value
                else:
                    held += value
                    if sum(c.isalpha() for c in held) >= VOICE_CHECK_CHARS and _voice_ok(held):
                        live = True
                        yield "delta", held
            if held and not live and _voice_ok(held):
                yield "delta", held  # short reply: checked as a whole
            # The reply is the last round that said something; text before a tool call is a draft
            # (it streams to the screen, then the stored reply replaces it).
            said = [b["text"] for b in content if b.get("text", "").strip()]
            if said:
                texts = said
            uses = [b["toolUse"] for b in content if "toolUse" in b]
            done_now = not uses or stop != "tool_use"
            only_buttons = bool(uses) and all(tu["name"] in BUTTON_TOOLS for tu in uses)
            # English, reasoning, or "I changed it" without a tool: ask once to answer properly.
            final = done_now or only_buttons
            nudge = _nudge("".join(said), st.changed) if final and not nudged else None
            if done_now and not nudge:
                break
            if texts and (nudge or not only_buttons):
                yield "delta", "\n"
            messages.append({"role": "assistant", "content": content})
            results: list[dict[str, Any]] = []
            for tu in [] if done_now else uses:
                result, summary = run_tool(tu["name"], tu.get("input") or {}, st)
                if summary:
                    yield "tool", {"name": tu["name"], "summary": summary}
                results.append({"toolResult": {"toolUseId": tu["toolUseId"], "content": [{"json": result}]}})
            if nudge:
                nudged = True
                results.append({"text": nudge})
            elif texts and only_buttons:
                break  # buttons only: the reply is already written, another round adds nothing
            messages.append({"role": "user", "content": results})
    except ClientError:
        log.exception("assistant model call failed")
        fallback = "지금은 AI가 답하지 못했어요. 잠시 후 다시 보내 주세요."
        texts.append(fallback)
        yield "delta", fallback
    reply = "".join(texts).strip()
    if reply and not _voice_ok(reply):
        log.warning("assistant reply replaced: not addressed to the employee")
        reply = SAFE_ASK if st.suggestions else SAFE_REPLY
    yield "done", (st, reply)
