"""Receipt image → structured fields. Prompt and schema are versioned here (owner: ② AI·데이터)."""

from typing import Any

from receiptflow_common.bedrock import call_tool
from receiptflow_common.config import get_settings
from receiptflow_common.domain import AI_FIELDS, CATEGORIES, CATEGORY_HINTS, normalize_fields

PROMPT_VERSION = "receipt-extract-v9"

SYSTEM = """당신은 한국 카드 결제 영수증·카드 매출전표에서 업무 지출 증빙 정보를 읽어 내는 도구입니다.
식당·카페뿐 아니라 주유·택시·주차·통행료·철도·숙박·문구·마트·택배·우편·도서·교육·출력 등
업무에서 결제하는 모든 종류의 영수증을 같은 기준으로 읽습니다.

공통
- 이미지에 실제로 보이는 값만 적습니다. 추측하지 말고, 보이지 않거나 읽을 수 없으면 null입니다.
- 흐리거나 잘려서 확신할 수 없는 필드는 uncertain_fields에 넣습니다.
- 고객 이름·전화번호·주소·계좌번호 같은 개인정보는 어떤 필드에도 적지 않습니다.
- 영수증이 아닌 이미지면 is_receipt를 false로 둡니다.

상호명·사업자번호
- 상호명은 돈을 받은 가맹점(가게·지점) 이름입니다. 플랫폼·운영사·광고 표제보다 가맹점명·지점명을 씁니다.
- 뒤에 붙은 점포코드(#53385처럼 # 뒤 숫자)와 전화번호는 뺍니다.
  '천사(1004)마트', '역삼2호점'처럼 이름에 들어 있는 숫자는 그대로 둡니다.
- 사업자번호는 가맹점의 번호이며 000-00-00000 형식으로 적습니다.
  하이픈 없이 10자리로 찍히거나 대표자명 옆에 붙어 있어도 같은 번호입니다.
- 전화번호(02-, 031-, 1588- 등)·계좌번호·가맹점번호를 사업자번호로 적지 않습니다.

거래 일시
- YYYY-MM-DD 또는 시각이 보이면 YYYY-MM-DDTHH:MM 형식입니다.
- 거래·승인·판매·결제 일시를 씁니다. 출력·재인쇄 일시, 입차 시각, 승차·출발 시각, 체크인 날짜는 쓰지 않습니다
  (주차는 출차·정산 시각이 결제 시각입니다).
- 바코드·거래번호 속 숫자로 날짜를 만들거나 고치지 않습니다. 날짜가 훼손돼 확정할 수 없으면 null입니다.

금액 (원 단위 정수, 쉼표·'원' 제외)
- total_amount는 할인·쿠폰·포인트 차감이 반영된 최종 결제금액입니다.
  할인 전 '합계'와 다르면 결제금액을 씁니다.
- supply_amount는 과세 공급가액(과세물품가액), vat_amount는 부가세,
  exempt_amount는 면세물품가액·면세 합계입니다.
- 0이 인쇄돼 있으면 0, 칸 자체가 없으면 null입니다. 계산해서 채우지 않습니다.
- 수량(주유 리터 등)은 금액이 아니므로 금액 필드에 넣지 않습니다.

카드 정보
- 결제수단은 '신용카드', '체크카드', '현금', '계좌이체', '기타' 중 하나입니다.
  카드종류·카드사명으로 판단합니다 ('KB국민체크', 'NH체크카드', '신한카드-체크' → 체크카드).
  헤더의 '신용카드 매출전표' 문구보다 카드사명이 우선입니다.
  카드 이름에 '체크'가 없는 일반 카드사·카드명(신한카드, 현대카드, 비씨카드, 삼성카드 등)은 신용카드입니다.
  선불·기프트·지역화폐 카드(예: 코나카드)는 '기타'입니다. 카드 이름이 아예 안 보이면 null입니다.
- card_issuer는 카드종류·카드명 그대로 적습니다 (예: '토스뱅크', '농협비씨신용', 'KB국민체크').
  '매입사'로 따로 찍힌 회사가 아니라 카드 이름입니다.
- card_number는 찍힌 모든 자리를 그대로 적습니다: 숫자, 가림 표시(*), 하이픈까지 (예: '9430-1178-****-558*').
  가려진 묶음(****)을 빼거나 줄이지 않고, 가려진 숫자를 추측해 채우지 않습니다.
  앞 8자리처럼 일부만 찍혀 있으면 찍힌 만큼만 적고, 안 찍힌 자리를 *로 덧붙이지 않습니다.
- '카드번호' 라벨 없이 카드사명 바로 아래·옆에 찍힌 8~16자리 숫자(일부 * 포함)도 card_number입니다.
- approval_number는 카드 승인번호입니다. 문자열로 적고 앞자리 0을 지우지 않으며, 숫자 사이 공백은 붙입니다.
  8자리가 아닐 수도 있습니다. 거래번호·주문번호·전표번호·영수증번호·가맹점번호는 승인번호가 아닙니다.

품목·분류
- items는 품목 요약 한 줄입니다 (예: '아메리카노 x4, 치즈케이크 x1', '휘발유 31.3L', 'KTX 서울→부산').
- category는 가게 종류·품목으로 판단한 지출 분류 제안입니다. 아래 코드 중 하나, 판단이 어려우면 null.
  식당·카페·편의점 먹거리는 food입니다. 접대·선물비(entertainment)는 영수증만으로 알 수 없으므로
  고르지 않습니다 (목적은 직원이 정함):
""" + "\n".join(f"  - {code}: {CATEGORIES[code]} — {hint}" for code, hint in CATEGORY_HINTS.items())

SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "is_receipt": {"type": "boolean"},
        "merchant_name": {"type": ["string", "null"], "description": "상호명"},
        "business_number": {"type": ["string", "null"], "description": "사업자등록번호"},
        "transaction_at": {"type": ["string", "null"], "description": "거래 일시"},
        "supply_amount": {"type": ["integer", "null"], "description": "공급가액"},
        "vat_amount": {"type": ["integer", "null"], "description": "부가세"},
        "exempt_amount": {"type": ["integer", "null"], "description": "면세물품가액·면세 합계"},
        "total_amount": {"type": ["integer", "null"], "description": "최종 결제금액 (할인 반영 후)"},
        "payment_method": {"type": ["string", "null"]},
        "card_issuer": {"type": ["string", "null"], "description": "카드사·카드 이름"},
        "card_number": {"type": ["string", "null"], "description": "찍힌 모든 자리 그대로 (숫자·*·하이픈)"},
        "approval_number": {"type": ["string", "null"], "description": "승인번호 (앞자리 0 유지)"},
        "items": {
            "type": ["string", "null"],
            "description": "품목 요약 한 줄 (예: '아메리카노 x4, 치즈케이크 x1'). 지출 목적 추천에 쓴다",
        },
        "category": {
            "type": ["string", "null"],
            "enum": [*CATEGORIES, None],
            "description": "지출 분류 제안",
        },
        "uncertain_fields": {"type": "array", "items": {"type": "string", "enum": list(AI_FIELDS)}},
    },
    "required": ["is_receipt", "merchant_name", "transaction_at", "total_amount", "uncertain_fields"],
}

CORE_FIELDS = ("merchant_name", "transaction_at", "total_amount")


class NotAReceipt(ValueError):
    pass


def _mock(_: bytes) -> tuple[dict[str, Any], dict[str, int]]:
    return (
        {
            "is_receipt": True,
            "merchant_name": "스타벅스 강남R점",
            "business_number": "201-81-21515",
            "transaction_at": "2026-10-14T12:31",
            "supply_amount": 12273,
            "vat_amount": 1227,
            "exempt_amount": None,
            "total_amount": 13500,
            "payment_method": "신용카드",
            "card_issuer": "신한카드",
            "card_number": "4518-42**-****-1234",
            "approval_number": "30012345",
            "category": "food",
            "items": "아메리카노 T x2, 카페라떼 G x1, 치즈케이크 x1",
            "uncertain_fields": [],
        },
        {"input_tokens": 0, "output_tokens": 0, "latency_ms": 0},
    )


def extract(
    image: bytes, model: str | None = None
) -> tuple[dict[str, Any], list[str], dict[str, int], dict[str, Any]]:
    """Return (fields, needs_check, usage, context). `context` is for the assistant, not a form field."""
    if get_settings().ai_mode == "mock":
        raw, usage = _mock(image)
    else:
        raw, usage = call_tool(
            SYSTEM,
            [
                {"image": {"format": "jpeg", "source": {"bytes": image}}},
                {"text": "이 영수증의 증빙 정보를 record_receipt 도구로 기록하세요."},
            ],
            "record_receipt",
            "영수증에서 읽은 증빙 정보를 기록한다",
            SCHEMA,
            model=model or get_settings().extract_model,
        )
    if raw.get("is_receipt") is False:
        raise NotAReceipt("영수증을 찾지 못했습니다. 영수증 전체가 보이게 다시 찍어 주세요.")
    # category is only a suggestion: the worker fills it when the employee has not chosen one yet.
    fields = normalize_fields({k: raw.get(k) for k in (*AI_FIELDS, "category")})
    uncertain = [k for k in raw.get("uncertain_fields") or [] if k in AI_FIELDS]
    needs_check = sorted(set(uncertain) | {k for k in CORE_FIELDS if fields.get(k) is None})
    items = raw.get("items")
    context = {"items": items.strip()[:300]} if isinstance(items, str) and items.strip() else {}
    return fields, needs_check, usage, context
