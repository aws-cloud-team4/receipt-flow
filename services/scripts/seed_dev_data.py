"""Fill the shared table and bucket with fake receipts for the developer-login test accounts.

uv run --with pillow python scripts/seed_dev_data.py                # about 150 receipts, as of now
uv run --with pillow python scripts/seed_dev_data.py --as-of 2026-11-14T11:00     # as of that moment
uv run python scripts/clear_dev_data.py                             # removes them (owner_sub dev-*)

The data tells the whole flow for a demo: drafts stopped mid-chat, a review queue, receipts sent back,
receipts fixed and sent again, and four months of approved ones, with different chats and histories.
`--as-of` (KST) dates everything up to that moment, so the set can be put in before a demo day; until
then the newest receipts show dates in the future. `--count` changes how many.

Everything is fictional: people from DEV_PROFILES, made-up shops, business and approval numbers, and
synthetic receipt images. The photos land in incoming/, so S3 still queues them for analysis, but every
receipt is marked `seed` and ocr-worker drops those messages without calling the model (no Bedrock cost;
workers from before that check analyse them). Re-running adds another set, so clear first.
"""

import argparse
import io
import random
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont
from receiptflow_common import aws
from receiptflow_common.auth import DEV_PROFILES
from receiptflow_common.config import get_settings
from receiptflow_common.domain import AI_FIELDS, CATEGORIES, FIELD_LABELS, duplicate_key, ro, run_checks
from receiptflow_common.org import KST
from receiptflow_common.store import _ddb, _pk

# Korean font: Windows 맑은 고딕, macOS Apple SD 산돌고딕, Linux 나눔고딕, else NanumGothic.ttf here.
FONTS = (
    "C:/Windows/Fonts/malgun.ttf",
    "/System/Library/Fonts/AppleSDGothicNeo.ttc",
    "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
)
FONT = next((f for f in FONTS if Path(f).exists()), "NanumGothic.ttf")
rng = random.Random(20261017)

# (category, shop, items with prices, purpose)
SHOPS: list[tuple[str, str, list[tuple[str, int]], str]] = [
    (
        "food",
        "한빛 김밥천국 역삼점",
        [("참치김밥", 4500), ("라볶이", 7500), ("돈까스", 9500)],
        "팀 점심 식사",
    ),
    ("food", "솥밥한상 선릉점", [("제육솥밥", 11000), ("된장찌개", 9000)], "프로젝트 회의 점심"),
    ("food", "카페 온더코너", [("아메리카노", 4500), ("카페라떼", 5000), ("크로플", 6500)], "외부 미팅 다과"),
    ("food", "늦은밤 국밥", [("순대국밥", 10000), ("수육", 18000)], "야근 식사"),
    (
        "entertainment",
        "한우명가 강남본점",
        [("한우 등심", 45000), ("된장전골", 12000)],
        "거래처 미팅 식사 (주)가온테크",
    ),
    ("entertainment", "꽃담 플라워", [("축하 화환", 100000)], "협력사 개업 축하 화환 (주)세움"),
    ("travel", "카카오T 블루", [("택시 운임", 23400)], "고객사 방문 택시"),
    ("travel", "코레일 서울역", [("KTX 서울-부산", 59800)], "부산 지사 출장"),
    ("travel", "스테이 해운대 호텔", [("숙박 1박", 98000)], "부산 지사 출장 숙박"),
    ("travel", "GS칼텍스 역삼주유소", [("휘발유", 70000)], "업무 차량 주유"),
    ("delivery", "CJ대한통운 역삼점", [("택배 2건", 8000)], "샘플 발송"),
    ("delivery", "우체국 강남우체국", [("등기우편", 4300)], "계약서 원본 발송"),
    ("supplies", "알파문구 역삼점", [("A4용지", 25000), ("볼펜", 4200)], "팀 사무용품"),
    ("supplies", "오피스디포 강남점", [("토너", 89000)], "프린터 토너 교체"),
    ("supplies", "하이마트 삼성점", [("모니터 27인치", 289000)], "신규 입사자 모니터"),
    ("education", "교보문고 강남점", [("클라우드 입문서", 32000), ("SQL 실습서", 28000)], "팀 스터디 도서"),
    ("education", "패스트캠퍼스", [("데이터 분석 강의", 150000)], "직무 교육"),
    ("welfare_event", "파티룸 모먼트", [("대관 3시간", 120000)], "팀 워크숍"),
    ("welfare_event", "케이크하우스 선릉점", [("생일 케이크", 38000)], "팀원 생일 축하"),
    ("subscription", "SKT 직영점", [("업무폰 요금", 55000)], "업무 전화 요금"),
    ("subscription", "Figma Korea", [("Professional 1석", 22000)], "디자인 툴 구독"),
    ("marketing", "애드프린트", [("전단지 1000매", 165000)], "신제품 홍보물 인쇄"),
    ("marketing", "굿즈팩토리", [("로고 텀블러 50개", 320000)], "전시회 판촉물"),
    ("other", "만능열쇠 수리점", [("회의실 도어락 수리", 45000)], "회의실 출입문 수리"),
]
ISSUERS = [
    ("신한카드", "신용카드"),
    ("KB국민체크", "체크카드"),
    ("삼성카드", "신용카드"),
    ("현대카드", "신용카드"),
]
# Change requests worded like the reviewer screen's defaults (web/src/reviewReasons.ts), by what went wrong.
PURPOSE_DETAIL = ("어떤 업무를 위해 쓴 비용인지 지출 목적을 구체적으로 적어 주세요.", ["purpose"])
RETAKE = ("사진이 흐려 내용을 확인하기 어려워요. 선명하게 다시 찍어 올려 주세요.", ["photo"])
NIGHT = ("심야에 결제한 업무상 사유를 지출 목적에 적어 주세요.", ["purpose"])
WEEKEND = ("주말에 결제한 업무상 사유를 지출 목적에 적어 주세요.", ["purpose"])
AI = "AI 어시스턴트"  # chat_service.agent.ACTOR
# the category the assistant may suggest first when the right one is a close call
NEAR = {
    "food": "welfare_event",
    "entertainment": "food",
    "travel": "other",
    "delivery": "supplies",
    "supplies": "other",
    "education": "supplies",
    "welfare_event": "food",
    "subscription": "other",
    "marketing": "supplies",
    "other": "supplies",
}
# how the employee answered a request about the purpose: (what they said, the purpose after the fix)
FIXES = {
    "night": ("릴리스 대응으로 야근하면서 쓴 비용이에요", "릴리스 대응 야근"),
    "weekend": ("주말 전시회 부스 운영 때문에 쓴 비용이에요", "주말 전시회 부스 운영"),
    "detail": ("3분기 실적 점검 회의 때 쓴 비용이에요", "3분기 실적 점검 회의"),
}


# where the receipt sits on the 760x960 canvas below (what the crop step would have found)
FRAME = [[70.0, 60.0], [690.0, 60.0], [690.0, 900.0], [70.0, 900.0]]


def iso(dt: datetime) -> str:
    return dt.astimezone(KST).isoformat(timespec="milliseconds")


def receipt_image(f: dict[str, Any], items: list[tuple[str, int, int]]) -> bytes:
    w, h = 560, 760
    img = Image.new("RGB", (w, h), (250, 249, 245))
    d = ImageDraw.Draw(img)

    def text(y: int, s: str, size: int = 20, align: str = "l") -> None:
        font = ImageFont.truetype(FONT, size)
        x, anchor = {"l": (36, "la"), "c": (w / 2, "ma"), "r": (w - 36, "ra")}[align]
        d.text((x, y), s, font=font, fill=(25, 25, 25), anchor=anchor)

    text(30, f["merchant_name"], 28, "c")
    text(78, f"사업자번호: {f['business_number']}")
    text(108, f"일시: {f['transaction_at'].replace('T', ' ')}")
    d.line((30, 146, w - 30, 146), fill=(90, 90, 90), width=2)
    y = 162
    for name, qty, price in items:
        text(y, f"{name} x{qty}")
        text(y, f"{price * qty:,}", align="r")
        y += 32
    d.line((30, y + 6, w - 30, y + 6), fill=(90, 90, 90), width=2)
    y += 22
    for label, key in (("공급가액", "supply_amount"), ("부가세", "vat_amount")):
        text(y, label)
        text(y, f"{f[key]:,}", align="r")
        y += 30
    text(y, "합계", 26)
    text(y, f"{f['total_amount']:,}", 26, "r")
    y += 50
    text(y, f"{f['card_issuer']} {f['payment_method']}  승인번호 {f['approval_number']}")
    text(y + 30, f"카드번호 {f['card_number']}")
    text(y + 80, "감사합니다", 20, "c")
    canvas = Image.new("RGB", (760, 960), (45, 48, 55))
    canvas.paste(img.rotate(rng.uniform(-4, 4), expand=True, fillcolor=(45, 48, 55)), (70, 60))
    out = io.BytesIO()
    canvas.save(out, "JPEG", quality=82)
    return out.getvalue()


def make_fields(
    shop: tuple[str, str, list[tuple[str, int]], str], at: datetime, department: str, whole: bool = False
) -> tuple[dict, list]:
    category, merchant, menu, purpose = shop
    if whole:  # the same bill again (a duplicate pair needs the same total)
        items = [(n, 1, p) for n, p in menu]
    else:
        items = [(n, rng.choice([1, 1, 2]), p) for n, p in rng.sample(menu, k=rng.randint(1, len(menu)))]
    total = sum(q * p for _, q, p in items)
    supply = round(total / 1.1)
    issuer, method = rng.choice(ISSUERS)
    fields = {
        "merchant_name": merchant,
        "business_number": f"{rng.randint(100, 899)}-{rng.randint(10, 99)}-{rng.randint(10000, 99999)}",
        "transaction_at": at.strftime("%Y-%m-%dT%H:%M"),
        "supply_amount": supply,
        "vat_amount": total - supply,
        "exempt_amount": None,
        "total_amount": total,
        "payment_method": method,
        "card_issuer": issuer,
        "card_number": f"{rng.randint(4000, 9999)}-****-****-{rng.randint(1000, 9999)}",
        "approval_number": f"{rng.randint(10000000, 99999999)}",
        "category": category,
        "purpose": purpose,
        "department": department,
    }
    return fields, items


def office_hours(dt: datetime) -> datetime:
    """People submit and review during the working day, Monday to Friday."""
    if dt.hour < 9:
        dt = dt.replace(hour=9, minute=rng.randint(0, 50))
    elif dt.hour >= 19:
        dt = (dt + timedelta(days=1)).replace(hour=9, minute=rng.randint(0, 50))
    while dt.weekday() >= 5:
        dt += timedelta(days=1)
    return dt


def timeline(at: datetime, story: str) -> list[tuple[str, datetime]]:
    """When each step of a story happened, oldest first, for something bought at `at`."""
    quick = rng.random() < 0.6 or story == "draft"  # written up right away, or the next day
    created = at + timedelta(minutes=rng.randint(20, 180) if quick else rng.randint(180, 26 * 60))
    if created.hour < 8:  # nobody writes up a receipt in the middle of the night
        created = created.replace(hour=rng.randint(8, 10), minute=rng.randint(0, 59))
    steps: list[tuple[str, datetime]] = [("created", created)]

    def then(step: str, low: int, high: int, office: bool = True) -> None:
        when = steps[-1][1] + timedelta(minutes=rng.randint(low, high))
        steps.append((step, office_hours(when) if office else when))

    if story != "draft":
        then("submitted", 4, 45, office=False)
    if story in ("sent_back", "resubmitted", "approved_after_fix"):
        then("changes_requested", 2 * 60, 40 * 60)
    if story in ("resubmitted", "approved_after_fix"):
        then("fixed", 60, 20 * 60)
        then("resubmitted", 3, 15, office=False)
    if story in ("approved", "approved_after_fix"):
        then("approved", 2 * 60, 48 * 60)
    return steps


def change_request(fields: dict[str, Any], codes: set[str]) -> tuple[str, list[str], str]:
    """(reason, fields to fix, how the employee fixes it) for a receipt the reviewer sends back."""
    if "late_night" in codes:
        return (*NIGHT, "night")
    if "weekend" in codes:
        return (*WEEKEND, "weekend")
    category = CATEGORIES.get(fields["category"], fields["category"])
    by_category = (
        f"지출 분류({category})가 지출 목적에 맞는지 확인하고 수정해 주세요.",
        ["category"],
        "category",
    )
    return rng.choice(
        [(*PURPOSE_DETAIL, "detail"), (*PURPOSE_DETAIL, "detail"), (*RETAKE, "retake"), by_category]
    )


def first_chat(fields: dict[str, Any], codes: set[str], unclear: list[str], upto: str) -> list[tuple]:
    """The first conversation as (role, text, extra). `upto`: "start" (stopped at the first question),
    "purpose" (stopped once the purpose is in) or "end"."""
    purpose, category = fields["purpose"], fields["category"]
    label = CATEGORIES[category]
    others = sorted({(p, c) for c, _, _, p in SHOPS if p != purpose})
    picks = [{"purpose": p, "category": c, "category_label": CATEGORIES[c]} for p, c in rng.sample(others, 2)]
    picks.insert(rng.randint(0, 2), {"purpose": purpose, "category": category, "category_label": label})
    talk: list[tuple] = [
        (
            "assistant",
            f"영수증을 읽었어요. {fields['merchant_name']}에서 {fields['total_amount']:,}원 "
            "결제하신 내역이에요. "
            "지출 목적과 분류를 알려 주세요. 추천을 누르거나 직접 적어 주세요.",
            {"slot": "purpose", "suggestions": picks},
        )
    ]
    if upto == "start":
        return talk
    style = (
        "partner" if category == "entertainment" else rng.choice(["pick"] * 3 + ["typed"] * 3 + ["changed"])
    )
    if style == "pick":
        talk.append(("user", purpose, {}))
        talk.append(("assistant", f"지출 목적은 “{purpose}”, 분류는 '{label}'{ro(label)} 넣었어요.", {}))
    elif style == "partner":
        short = purpose.split(" (")[0]
        partner = purpose.split("(", 1)[1].rstrip(")") if "(" in purpose else "협력사"
        talk.append(("user", short, {}))
        talk.append(
            (
                "assistant",
                "접대·선물비는 상대 회사를 함께 적어야 해요. 어느 회사와 함께하셨나요?",
                {"slot": "purpose"},
            )
        )
        talk.append(("user", f"{partner} 담당자분들이요", {}))
        talk.append(
            (
                "assistant",
                f"지출 목적을 “{purpose}”{ro(purpose)} 정리하고 분류는 '{label}'{ro(label)} 넣었어요.",
                {},
            )
        )
    else:
        wrong = CATEGORIES[NEAR[category]]
        guess = wrong if style == "changed" else label
        talk.append(("user", f"{purpose} 때문에 썼어요", {}))
        talk.append(
            (
                "assistant",
                f"지출 목적을 “{purpose}”{ro(purpose)} 적었어요. 분류는 '{guess}'{ro(guess)} 할까요?",
                {"slot": "category", "choices": ["예", "아니요"]},
            )
        )
        if upto == "purpose":
            return talk
        if style == "changed":
            options = [label, *rng.sample([v for v in CATEGORIES.values() if v not in (label, wrong)], 2)]
            rng.shuffle(options)
            talk.append(("user", "아니요", {}))
            talk.append(("assistant", "그럼 어떤 분류가 맞을까요?", {"slot": "category", "choices": options}))
            talk.append(("user", label, {}))
            talk.append(("assistant", f"분류를 '{label}'{ro(label)} 바꿨어요.", {}))
        else:
            talk.append(("user", "예", {}))
            talk.append(("assistant", f"분류를 '{label}'{ro(label)} 넣었어요.", {}))
    if upto == "purpose":
        return talk
    warn = [w for c, w in (("late_night", "심야"), ("weekend", "주말")) if c in codes]
    if warn:
        talk.append(
            (
                "assistant",
                f"{'·'.join(warn)} 거래예요. 업무 지출이면 지출 목적에 사유를 함께 적어 두시면 "
                "검수가 빨라져요.",
                {},
            )
        )
    if "amount_mismatch" in codes:
        talk.append(
            (
                "assistant",
                "공급가액과 부가세를 더한 값이 총액과 달라요. 확인 화면에서 사진과 비교해 고쳐 주시겠어요?",
                {"slot": "confirm", "choices": ["직접 수정", "값이 맞아요"]},
            )
        )
        return talk
    if unclear:
        names = ", ".join(FIELD_LABELS[k] for k in unclear)
        talk.append(
            (
                "assistant",
                f"{names} 값을 정확히 읽지 못했어요. 확인 화면에서 사진과 비교해 고쳐 주시겠어요?",
                {"slot": "confirm", "choices": ["직접 수정", "값이 맞아요"]},
            )
        )
        talk.append(("user", "값이 맞아요", {}))
    talk.append(
        ("assistant", "필요한 정보가 모두 모였어요. 확인 화면에서 내용을 살펴보고 제출해 주세요.", {})
    )
    return talk


def sent_back_chat(reviewer: str, reason: str, review_fields: list[str], reviewed_at: str) -> list[tuple]:
    """What chat-service says once when a receipt comes back (chat_service.main._changes_turn)."""
    text = f"{reviewer}님이 보완을 요청했어요: “{reason}”"
    if "photo" in review_fields:
        text += " 사진을 다시 찍어 올려 주세요. 다시 올리면 처음부터 다시 작성해요."
        choices = ["다시 찍기"]
    else:
        names = ", ".join(FIELD_LABELS[k] for k in review_fields)
        particle = "을" if (ord(names[-1]) - 0xAC00) % 28 else "를"
        text += f" {names}{particle} 고친 뒤 [제출하기]로 내용을 확인하고 다시 제출해 주세요."
        text += " 어떻게 고칠지 말씀해 주셔도 돼요."
        choices = ["직접 수정"]
    return [
        ("event", "changes_requested", {"event": "changes_requested", "reviewed_at": reviewed_at}),
        ("assistant", text, {"choices": choices}),
    ]


def put_receipt(plan: dict[str, Any], now: datetime, reviewers: list[str]) -> dict[str, Any]:
    """Write one receipt with its history, chat and photo. `plan`: owner, shop, at, story, and optionally
    tweak ("mismatch"), whole, same_card, duplicate_of, same_approval_of."""
    owner, story, at = plan["owner"], plan["story"], plan["at"]
    name, department, position, employee_no, _ = DEV_PROFILES[owner]
    fields, items = make_fields(plan["shop"], at, department, plan.get("whole", False))
    fields.update(plan.get("same_card", {}))  # the same bill sent twice
    if plan.get("tweak") == "mismatch":
        fields["vat_amount"] += 1000  # amount check fails: supply + VAT != total (cannot be submitted)
    read = [k for k in AI_FIELDS if fields.get(k) not in (None, "")]
    # a few receipts give the reviewer more to look at: a blurry field, a value the employee typed
    unclear = (
        [rng.choice(["approval_number", "business_number", "card_number"])] if rng.random() < 0.15 else []
    )
    typed = [rng.choice(["payment_method", "merchant_name", "total_amount"])] if rng.random() < 0.15 else []
    skipped_confirm = story != "draft" and rng.random() < 0.1
    reviewer = rng.choice(reviewers)
    rid = uuid.uuid4().hex
    sub = f"dev-{owner}"

    # the timeline, oldest first; a story that would run past `now` starts a day earlier
    steps = timeline(at, story)
    while steps[-1][1] > now - timedelta(minutes=rng.randint(5, 40)):
        at -= timedelta(days=1)
        steps = timeline(at, story)
    fields["transaction_at"] = at.strftime("%Y-%m-%dT%H:%M")
    when = dict(steps)
    created = when["created"]
    checks = run_checks(fields, plan.get("duplicate_of"), plan.get("same_approval_of"))
    codes = {c["code"] for c in checks}

    events: list[tuple[datetime, str, str, str | None]] = [(created, name, "created", None)]
    upto = (
        "end" if story != "draft" or "amount_mismatch" in codes else rng.choice(["start", "purpose", "end"])
    )
    talk = first_chat(fields, codes, unclear, upto)
    final = dict(fields)  # what is stored: after the employee's answers and fixes
    if upto == "start":
        final.update(purpose=None, category=None)
    else:
        events.append((created + timedelta(minutes=3), AI, "ai_edited", "지출 목적, 지출 분류 (사용자 요청)"))
    if typed:
        events.append((created + timedelta(minutes=5), name, "edited", f"{FIELD_LABELS[typed[0]]} 수정"))
    messages = [(created + timedelta(minutes=2, seconds=35 * i), *m) for i, m in enumerate(talk)]

    review: dict[str, Any] = {}
    if "submitted" in when:
        events.append((when["submitted"], name, "submitted", None))
    if "changes_requested" in when:
        reason, review_fields, fix = change_request(fields, codes)
        back = when["changes_requested"]
        events.append((back, reviewer, "changes_requested", reason))
        review = {
            "reviewed_by": reviewer,
            "reviewed_at": iso(back),
            "review_note": reason,
            "review_fields": review_fields,
        }
        seen = when.get("fixed") or back + timedelta(minutes=rng.randint(20, 200))
        if "fixed" in when or (seen < now and rng.random() < 0.6):  # opened it and was told what to fix
            told = sent_back_chat(reviewer, reason, review_fields, iso(back))
            messages += [(seen + timedelta(seconds=i), *m) for i, m in enumerate(told)]
        if "fixed" in when:
            fixed = when["fixed"] + timedelta(minutes=1)
            if fix == "retake":  # a new photo starts the receipt over, and the chat with it
                events.append((fixed, name, "reuploaded", "처음부터 다시 작성"))
                again = first_chat(fields, codes, [], "end")
                messages = [(fixed + timedelta(minutes=1, seconds=35 * i), *m) for i, m in enumerate(again)]
                events.append(
                    (fixed + timedelta(minutes=2), AI, "ai_edited", "지출 목적, 지출 분류 (사용자 요청)")
                )
            else:
                if fix == "category":
                    said = "분류는 지금 것이 맞아요. 목적을 더 자세히 적을게요"
                    final["purpose"] = f"{fields['purpose']} (부서 예산 집행 건)"
                elif fix == "detail":
                    said, final["purpose"] = FIXES[fix][0], f"{fields['purpose']} ({FIXES[fix][1]})"
                else:
                    said, final["purpose"] = FIXES[fix][0], f"{fields['purpose']} ({FIXES[fix][1]})"
                answer = (
                    f"지출 목적을 “{final['purpose']}”{ro(final['purpose'])} 고쳤어요. "
                    "[제출하기]로 내용을 확인하고 다시 제출해 주세요."
                )
                messages.append((fixed, "user", said, {}))
                messages.append((fixed + timedelta(seconds=20), "assistant", answer, {}))
                events.append((fixed + timedelta(seconds=20), AI, "ai_edited", "지출 목적 (사용자 요청)"))
            events.append((when["resubmitted"], name, "submitted", None))
            review["review_note"] = None  # cleared when it is submitted again
    if "approved" in when:
        events.append((when["approved"], reviewer, "approved", None))
        review = {
            "reviewed_by": reviewer,
            "reviewed_at": iso(when["approved"]),
            "review_note": None,
            "review_fields": [],
        }

    status = {
        "draft": "draft",
        "submitted": "submitted",
        "resubmitted": "submitted",
        "sent_back": "changes_requested",
    }.get(story, "approved")
    submitted = when.get("resubmitted") or when.get("submitted")
    updated = steps[-1][1]
    item: dict[str, Any] = {
        "pk": _pk(rid),
        "sk": "META",
        "id": rid,
        "owner_sub": sub,
        "owner_name": name,
        "owner_profile": {"employee_no": employee_no, "department": department, "position": position},
        "processing": "server",
        "analysis_status": "done",
        "review_status": status,
        "fields": final,
        "needs_check": [k for k in unclear if k not in typed],
        "ai_filled": [k for k in read if k not in typed],  # read by AI and not edited since
        "ai_context": {"items": ", ".join(f"{n} x{q}" for n, q, _ in items)},
        "checks": checks,
        "dup_key": duplicate_key(final),
        "image_key": f"incoming/{rid}.jpg",
        # the photo went through the server crop, so reviewers can open the original too
        "preprocess": {
            "where": "server",
            "corners": FRAME,
            "detected_corners": FRAME,
            "adjusted": False,
            "blur_score": round(rng.uniform(120, 480), 1),
            "width": 760,
            "height": 960,
            "elapsed_ms": rng.randint(60, 180),
        },
        "result_confirmed_at": (
            iso(created + timedelta(minutes=2)) if status != "draft" and not skipped_confirm else None
        ),
        "created_at": iso(created),
        "updated_at": iso(updated),
        "submitted_at": iso(submitted) if submitted else None,
        "timings": {
            "created": iso(created),
            "uploaded": iso(created),
            "analysis_started": iso(created + timedelta(seconds=2)),
            "analysis_finished": iso(created + timedelta(seconds=rng.randint(6, 12))),
            **(
                {
                    "chat_first_question": iso(created + timedelta(minutes=2)),
                    "chat_last_answer": iso(created + timedelta(minutes=5)),
                    "submitted": iso(submitted),
                }
                if submitted
                else {}
            ),
        },
        "gsi1pk": f"OWNER#{sub}",
        "gsi1sk": iso(created),
        "gsi2pk": f"STATUS#{status}",
        "gsi2sk": iso(updated),
        "seed": "dev",
        **review,
    }
    table = aws.table()
    table.put_item(Item=_ddb(item))
    with table.batch_writer() as batch:
        for at_event, actor, action, note in events:
            batch.put_item(
                Item={
                    "pk": _pk(rid),
                    "sk": f"EVENT#{iso(at_event)}#{uuid.uuid4().hex[:6]}",
                    "at": iso(at_event),
                    "actor": actor,
                    "action": action,
                    "note": note,
                }
            )
        for at_msg, role, text, extra in messages:
            row = {"at": iso(at_msg), "role": role, "text": text, **extra}
            batch.put_item(
                Item=_ddb({"pk": _pk(rid), "sk": f"MSG#{iso(at_msg)}#{uuid.uuid4().hex[:6]}", **row})
            )
    jpg = receipt_image(fields, items)
    s3, bucket = aws.client("s3"), get_settings().bucket
    for prefix in ("raw", "incoming"):
        s3.put_object(Bucket=bucket, Key=f"{prefix}/{rid}.jpg", Body=jpg, ContentType="image/jpeg")
    return item


# share of each story, and how many days before `now` the purchase was made
STORIES = {
    "draft": (0.07, (0, 2)),  # being written, some stopped mid-chat
    "submitted": (0.14, (0, 5)),  # the review queue
    "resubmitted": (0.04, (3, 9)),  # sent back, fixed, waiting again
    "sent_back": (0.10, (2, 14)),  # waiting for the employee
    "approved_after_fix": (0.10, (9, 110)),
    "approved": (0.55, (4, 120)),
}


def shop(name: str) -> tuple[str, str, list[tuple[str, int]], str]:
    return next(s for s in SHOPS if s[1].startswith(name))


def stories(now: datetime) -> list[dict[str, Any]]:
    """Receipts that belong together, so a viewer can follow one: a trip, a double submission."""

    def day(ago: int, hour: int, minute: int) -> datetime:
        return (now - timedelta(days=ago)).replace(hour=hour, minute=minute)

    monitor = {"owner": "lee", "shop": shop("하이마트"), "at": day(4, 13, 20), "whole": True}
    return [
        # 김민준's Busan trip three weeks ago: all approved
        {"owner": "kim", "shop": shop("코레일"), "at": day(22, 7, 40), "story": "approved"},
        {"owner": "kim", "shop": shop("카카오T"), "at": day(22, 11, 5), "story": "approved"},
        {"owner": "kim", "shop": shop("한우명가"), "at": day(22, 19, 20), "story": "approved_after_fix"},
        {"owner": "kim", "shop": shop("스테이 해운대"), "at": day(21, 8, 30), "story": "approved"},
        # 윤지호's trip this week: still in the review queue
        {"owner": "yoon", "shop": shop("코레일"), "at": day(3, 8, 15), "story": "submitted"},
        {"owner": "yoon", "shop": shop("스테이 해운대"), "at": day(2, 9, 0), "story": "submitted"},
        {"owner": "yoon", "shop": shop("카카오T"), "at": day(2, 14, 30), "story": "submitted"},
        # 이서연 sent the same monitor receipt twice: the second one is flagged as a duplicate
        {**monitor, "story": "approved", "key": "monitor"},
        {**monitor, "story": "submitted", "copy_of": "monitor"},
        # an amount the employee still has to fix before it can be submitted
        {
            "owner": "choi",
            "shop": shop("애드프린트"),
            "at": day(1, 15, 45),
            "story": "draft",
            "tweak": "mismatch",
        },
        {
            "owner": "kang",
            "shop": shop("알파문구"),
            "at": day(0, 9, 5),
            "story": "draft",
            "tweak": "mismatch",
        },
        # late-night spending the reviewer asks about
        {"owner": "jung", "shop": shop("늦은밤 국밥"), "at": day(8, 23, 25), "story": "sent_back"},
        {"owner": "jung", "shop": shop("늦은밤 국밥"), "at": day(12, 22, 50), "story": "approved_after_fix"},
        {"owner": "han", "shop": shop("카카오T"), "at": day(1, 23, 40), "story": "submitted"},
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description="Fake receipts for the developer-login test accounts.")
    parser.add_argument(
        "--as-of", help="KST moment to date the data up to, e.g. 2026-11-14T11:00 (default: now)"
    )
    parser.add_argument("--count", type=int, default=150, help="about how many receipts (default 150)")
    args = parser.parse_args()
    now = datetime.fromisoformat(args.as_of).replace(tzinfo=KST) if args.as_of else datetime.now(KST)
    employees = [k for k, v in DEV_PROFILES.items() if v[4] == "employee"]
    reviewers = [DEV_PROFILES[k][0] for k, v in DEV_PROFILES.items() if v[4] == "reviewer"]

    plans = stories(now)
    pool = [story for story, (share, _) in STORIES.items() for _ in range(round(share * args.count))]
    rng.shuffle(pool)
    for n, story in enumerate(pool[: max(0, args.count - len(plans))]):
        low, high = STORIES[story][1]
        at = (now - timedelta(days=rng.randint(low, high))).replace(
            hour=rng.randint(8, 20), minute=rng.randint(0, 59)
        )
        if at.weekday() >= 5 and rng.random() < 0.75:  # most spending is on working days
            at -= timedelta(days=at.weekday() - 4)
        if rng.random() < 0.08:  # some late-night spending (flagged for the reviewer)
            at = at.replace(hour=rng.choice([22, 23]))
        plans.append(
            {"owner": employees[n % len(employees)], "shop": rng.choice(SHOPS), "at": at, "story": story}
        )

    count: dict[str, int] = {}
    kept: dict[str, dict[str, Any]] = {}
    for plan in sorted(plans, key=lambda p: "copy_of" in p):  # originals before their copies
        if plan["at"] >= now:
            plan["at"] = now - timedelta(minutes=rng.randint(60, 240))
        first = kept.get(plan.get("copy_of", ""))
        if first:
            card = ("business_number", "payment_method", "card_issuer", "card_number", "approval_number")
            plan.update(
                duplicate_of=first["id"],
                same_approval_of=first["id"],
                same_card={k: first["fields"][k] for k in card},
            )
        item = put_receipt(plan, now, reviewers)
        if plan.get("key"):
            kept[plan["key"]] = item
        count[item["review_status"]] = count.get(item["review_status"], 0) + 1
    print(f"fake receipts as of {now:%Y-%m-%d %H:%M}:", sum(count.values()), count)


if __name__ == "__main__":
    main()
