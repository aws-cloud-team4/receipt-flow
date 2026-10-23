"""Receipt fields, state machine and automatic checks (see docs/contract.md)."""

import re
from datetime import UTC, datetime
from typing import Any

AI_FIELDS = (
    "merchant_name",
    "business_number",
    "transaction_at",
    "supply_amount",
    "vat_amount",
    "exempt_amount",
    "total_amount",
    "payment_method",
    "card_issuer",
    "card_number",
    "approval_number",
)
# Fixed expense categories (code -> label). Stored as the code; the UI and CSV show the label.
CATEGORIES = {
    "food": "식사·간식비",
    "entertainment": "접대·선물비",
    "travel": "교통·출장비",
    "delivery": "우편·배송비",
    "supplies": "사무용품·소모품비",
    "education": "도서·교육비",
    "welfare_event": "행사·복리후생비",
    "subscription": "통신·구독비",
    "marketing": "광고·홍보비",
    "other": "기타 업무비",
}
# Codes and labels used before the list was revised (2026-10-16); read as the new codes.
OLD_CODES = {
    "meal": "food",
    "team_dinner": "food",
    "meeting": "food",
    "transport": "travel",
    "postage": "delivery",
}
OLD_LABELS = {
    "식대": "food",
    "회식비": "food",
    "회의비": "food",
    "접대비": "entertainment",
    "교통비": "travel",
    "출장비": "travel",
    "사무용품·소모품": "supplies",
    "소모품비": "supplies",
    "통신·우편비": "delivery",
    "기타": "other",
}
CATEGORY_HINTS = {
    "food": "업무 식사, 야근 식사, 회식, 회의 다과, 탕비실 간식 (식당, 카페, 베이커리, 편의점·마트 먹거리)",
    "entertainment": "업무상 접대 식사, 외부 관계자 선물·경조 화환 (영수증만으로 확정하지 않음)",
    "travel": "택시·대중교통, 주유·충전, 주차·통행료, 철도·항공, 숙박, 업무 차량 정비",
    "delivery": "우편·등기, 택배, 퀵서비스, 샘플 발송",
    "supplies": "문구, 복사용지, 토너, 청소·구급용품(상비약), 컴퓨터·모니터·프린터, 책상·의자",
    "education": "업무 관련 도서, 강의, 세미나, 직무교육",
    "welfare_event": "워크숍, 사내 행사, 임직원 경조 화환·선물",
    "subscription": "업무 전화·인터넷, 소프트웨어 구독, 클라우드, API, 호스팅",
    "marketing": "온라인 광고, 홍보물 인쇄, 판촉물 제작, 전시 부스",
    "other": "시설·기기 수리 등 위에 해당하지 않는 업무 지출 (목적을 구체적으로)",
}
EXPENSE_FIELDS = ("category", "purpose")
# Copied from the login profile when the receipt is created; never edited in the service.
PROFILE_FIELDS = ("department",)
EDITABLE_FIELDS = AI_FIELDS + EXPENSE_FIELDS
ALL_FIELDS = EDITABLE_FIELDS + PROFILE_FIELDS
AMOUNT_FIELDS = ("supply_amount", "vat_amount", "exempt_amount", "total_amount")
REQUIRED_FIELDS = ("merchant_name", "transaction_at", "total_amount", "category", "purpose")

FIELD_LABELS = {
    "merchant_name": "상호명",
    "business_number": "사업자번호",
    "transaction_at": "거래 일시",
    "supply_amount": "공급가액",
    "vat_amount": "부가세",
    "exempt_amount": "면세금액",
    "total_amount": "총액",
    "payment_method": "결제수단",
    "card_issuer": "카드사",
    "card_number": "카드번호",
    "approval_number": "승인번호",
    "category": "지출 분류",
    "purpose": "지출 목적",
    "department": "부서",
}

ANALYSIS_STATUSES = ("waiting", "queued", "processing", "done", "failed")
REVIEW_STATUSES = ("draft", "submitted", "approved", "changes_requested")
REVIEW_LABELS = {
    "draft": "작성 중",
    "submitted": "제출",
    "approved": "승인",
    "changes_requested": "보완 요청",
}
EDITABLE_STATUSES = ("draft", "changes_requested")

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}(:\d{2})?)?$")


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def to_amount(value: Any) -> int | None:
    """Accept 12000, "12,000", "12,000원" → 12000."""
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return int(value)
    digits = re.sub(r"[^\d-]", "", str(value))
    return int(digits) if digits not in ("", "-") else None


def to_category(value: Any) -> str | None:
    """Accept a category code or its label ("식사·간식비" -> "food"), old ones included. Else None."""
    if value in (None, ""):
        return None
    text = str(value).strip()
    if text in CATEGORIES:
        return text
    by_label = {label: code for code, label in CATEGORIES.items()}
    return by_label.get(text) or OLD_CODES.get(text) or OLD_LABELS.get(text)


def card_number_as_printed(value: Any) -> str | None:
    """The card number exactly as the receipt prints it: partial, full or masked (* kept).

    Only surrounding spaces are trimmed and inner runs of spaces become one.
    """
    if value in (None, ""):
        return None
    return re.sub(r"\s+", " ", str(value)).strip() or None


def normalize_fields(raw: dict[str, Any]) -> dict[str, Any]:
    """Keep known keys only, trim strings, coerce amounts and categories. Empty values become None."""
    out: dict[str, Any] = {}
    for key, value in raw.items():
        if key not in ALL_FIELDS:
            continue
        if key in AMOUNT_FIELDS:
            out[key] = to_amount(value)
        elif key == "category":
            out[key] = to_category(value)
        elif key == "card_number":
            out[key] = card_number_as_printed(value)
        elif key == "approval_number":
            out[key] = re.sub(r"\s+", "", str(value)) if value is not None else None
            out[key] = out[key] or None
        elif key == "transaction_at" and value is not None:
            text = str(value).strip().replace(" ", "T")
            out[key] = (text[:16] if _DATE_RE.match(text) else text) or None  # minutes are enough
        elif value is None:
            out[key] = None
        else:
            text = str(value).strip()
            out[key] = text or None
    return out


# digits read in Korean: 0 영, 1 일, 3 삼, 6 육, 7 칠, 8 팔 end in a final consonant
_DIGIT_FINAL = {"0": "ㅇ", "1": "ㄹ", "3": "ㅁ", "6": "ㄱ", "7": "ㄹ", "8": "ㄹ"}


def ro(word: str) -> str:
    """The particle 로/으로 for `word`: 로 after a vowel or ㄹ, 으로 after any other final consonant.
    Closing brackets and quotes are skipped; a word ending in Latin letters gets (으)로."""
    for ch in reversed(word.strip()):
        if ch in ")]}'\"’” ":
            continue
        if "가" <= ch <= "힣":
            final = (ord(ch) - 0xAC00) % 28
            return "로" if final in (0, 8) else "으로"  # 8 = ㄹ
        if ch.isdigit():
            return "로" if _DIGIT_FINAL.get(ch) in (None, "ㄹ") else "으로"
        break
    return "(으)로"


def missing_required(fields: dict[str, Any]) -> list[str]:
    return [k for k in REQUIRED_FIELDS if fields.get(k) in (None, "")]


def parse_transaction_at(value: str | None) -> datetime | None:
    if not value or not _DATE_RE.match(value):
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def run_checks(
    fields: dict[str, Any], duplicate_of: str | None = None, same_approval_of: str | None = None
) -> list[dict[str, str]]:
    checks: list[dict[str, str]] = []
    supply, vat, exempt, total = (fields.get(k) for k in AMOUNT_FIELDS)
    # Marts, post offices and bookshops print a tax-exempt part next to supply + VAT.
    if supply is not None and vat is not None and total is not None and supply + vat + (exempt or 0) != total:
        parts = f"공급가액 {supply:,} + 부가세 {vat:,}" + (f" + 면세 {exempt:,}" if exempt else "")
        checks.append(
            {
                "code": "amount_mismatch",
                "level": "error",
                "message": f"{parts} = {supply + vat + (exempt or 0):,}원으로 총액 {total:,}원과 달라요.",
            }
        )
    raw_at = fields.get("transaction_at")
    at = parse_transaction_at(raw_at)
    if raw_at and at is None:
        checks.append({"code": "bad_date", "level": "error", "message": "거래 일시 형식을 확인해 주세요."})
    if at is not None:
        if "T" in raw_at and (at.hour >= 22 or at.hour < 6):
            checks.append(
                {
                    "code": "late_night",
                    "level": "warn",
                    "message": "심야(22시~06시) 거래예요. 업무 지출이면 목적에 사유를 적어 주세요.",
                }
            )
        if at.weekday() >= 5:
            checks.append(
                {
                    "code": "weekend",
                    "level": "warn",
                    "message": "주말 거래예요. 업무 지출이면 목적에 사유를 적어 주세요.",
                }
            )
    if duplicate_of:
        checks.append(
            {
                "code": "duplicate",
                "level": "warn",
                "message": f"같은 상호·일자·금액 증빙이 이미 있습니다 ({duplicate_of[:8]}).",
            }
        )
    if same_approval_of:
        checks.append(
            {
                "code": "same_approval",
                "level": "warn",
                "message": (
                    f"같은 카드 승인번호의 증빙이 이미 있습니다 ({same_approval_of[:8]}). "
                    "중복 제출인지 확인해 주세요."
                ),
            }
        )
    return checks


def duplicate_key(fields: dict[str, Any]) -> str | None:
    name, at, total = fields.get("merchant_name"), fields.get("transaction_at"), fields.get("total_amount")
    if not (name and at and total is not None):
        return None
    return f"{re.sub(r'\s+', '', name).lower()}|{at[:10]}|{total}"


def review_points(receipt: dict[str, Any]) -> list[dict[str, Any]]:
    """What a reviewer should look at first, by rule: [{level, code, text, fields}].

    `code` names the kind of point and `fields` the fields it is about, so the web can turn a
    point into a change request (docs/contract.md).
    """
    f = receipt.get("fields") or {}

    def point(level: str, code: str, text: str, fields: list[str] | None = None) -> dict[str, Any]:
        return {"level": level, "code": code, "text": text, "fields": fields or []}

    points = [point(c["level"], c["code"], c["message"]) for c in receipt.get("checks", [])]
    labels = lambda keys: ", ".join(FIELD_LABELS[k] for k in keys)  # noqa: E731
    unclear = [k for k in receipt.get("needs_check", []) if k in FIELD_LABELS]
    if unclear:
        text = f"흐리게 읽힌 칸 {labels(unclear)} — 사진과 비교해 보세요."
        points.append(point("warn", "unclear_fields", text, unclear))
    if receipt.get("analysis_status") == "failed":
        points.append(point("warn", "analysis_failed", "AI가 영수증을 읽지 못해 직원이 직접 입력했어요."))
    elif receipt.get("analysis_status") == "done":
        ai = set(receipt.get("ai_filled", []))
        typed = [k for k in AI_FIELDS if f.get(k) not in (None, "") and k not in ai]
        if typed:
            money = any(k in AMOUNT_FIELDS for k in typed)
            text = f"직원이 직접 입력·수정한 칸 {labels(typed)}" + (
                " — 금액은 사진과 꼭 비교하세요." if money else ""
            )
            points.append(point("warn" if money else "info", "edited_fields", text, typed))
        if not receipt.get("result_confirmed_at"):
            points.append(point("info", "result_unconfirmed", "직원이 AI가 읽은 결과 확인을 건너뛰었어요."))
    purpose = (f.get("purpose") or "").strip()
    if f.get("category") == "entertainment":
        text = "접대·선물비 — 지출 목적에 상대 거래처가 적혀 있는지 확인하세요."
        points.append(point("warn", "entertainment", text, ["purpose"]))
    if f.get("category") == "other":
        text = "기타 업무비 — 사용 목적이 구체적인지 확인하세요."
        points.append(point("info", "other_category", text, ["purpose"]))
    elif purpose and len(purpose) < 5:
        points.append(
            point("info", "short_purpose", "지출 목적이 짧아요. 구체적인지 확인하세요.", ["purpose"])
        )
    return points
