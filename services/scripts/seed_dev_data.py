"""Fill the shared table and bucket with fake receipts for the developer-login test accounts.

uv run --with pillow python scripts/seed_dev_data.py          # about 40 receipts over the last 3 months
uv run python scripts/clear_dev_data.py                        # removes them again (owner_sub dev-*)

Everything is fictional: people from DEV_PROFILES, made-up shops, business and approval numbers, and
synthetic receipt images. The photos land in incoming/, so S3 still queues them for analysis, but every
receipt is marked `seed` and ocr-worker drops those messages without calling the model (no Bedrock cost;
workers from before that check analyse them). Re-running adds another set, so clear first.
"""

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
from receiptflow_common.domain import AI_FIELDS, CATEGORIES, duplicate_key, run_checks
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
MISMATCH = (
    "공급가액·부가세와 총액이 맞지 않아요. 영수증과 비교해 금액을 수정해 주세요.",
    ["supply_amount", "vat_amount", "total_amount"],
)


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
    shop: tuple[str, str, list[tuple[str, int]], str], at: datetime, department: str
) -> tuple[dict, list]:
    category, merchant, menu, purpose = shop
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


def change_request(fields: dict[str, Any], tweak: str | None) -> tuple[str, list[str]]:
    if tweak == "mismatch":
        return MISMATCH
    if tweak == "night":
        return NIGHT
    category = CATEGORIES.get(fields["category"], fields["category"])
    by_category = (f"지출 분류({category})가 지출 목적에 맞는지 확인하고 수정해 주세요.", ["category"])
    return rng.choice([PURPOSE_DETAIL, RETAKE, by_category])


def put_receipt(
    owner: str, shop, at: datetime, status: str, reviewer: str | None, now: datetime, tweak: str | None
) -> str:
    name, department, position, employee_no, _ = DEV_PROFILES[owner]
    fields, items = make_fields(shop, at, department)
    if tweak == "night":
        fields["transaction_at"] = at.replace(hour=23, minute=rng.randint(5, 50)).strftime("%Y-%m-%dT%H:%M")
    if tweak == "mismatch":
        fields["vat_amount"] += 1000  # amount check fails: supply + VAT != total
    read = [k for k in AI_FIELDS if fields.get(k) not in (None, "")]
    # a few receipts give the reviewer more to look at: a blurry field, a value the employee typed
    unclear = (
        [rng.choice(["approval_number", "business_number", "card_number"])] if rng.random() < 0.15 else []
    )
    typed = [rng.choice(["payment_method", "merchant_name", "total_amount"])] if rng.random() < 0.15 else []
    skipped_confirm = status != "draft" and rng.random() < 0.1
    rid = uuid.uuid4().hex
    created = at + timedelta(hours=rng.randint(1, 30))
    if created > now:
        created = now - timedelta(hours=1)
    submitted = created + timedelta(minutes=rng.randint(3, 40)) if status != "draft" else None
    reviewed = (
        submitted + timedelta(hours=rng.randint(2, 60))
        if status in ("approved", "changes_requested")
        else None
    )
    if reviewed and reviewed > now:
        reviewed = now - timedelta(minutes=10)
    updated = reviewed or submitted or created
    sub = f"dev-{owner}"
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
        "fields": fields,
        "needs_check": [k for k in unclear if k not in typed],
        "ai_filled": [k for k in read if k not in typed],  # read by AI and not edited since
        "ai_context": {"items": ", ".join(f"{n} x{q}" for n, q, _ in items)},
        "checks": run_checks(fields),
        "dup_key": duplicate_key(fields),
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
    }
    events = [(created, name, "created", None)]
    if submitted:
        events.append((submitted, name, "submitted", None))
    if status == "approved":
        item.update(reviewed_by=reviewer, reviewed_at=iso(reviewed))
        events.append((reviewed, reviewer, "approved", None))
    if status == "changes_requested":
        reason, review_fields = change_request(fields, tweak)
        item.update(
            reviewed_by=reviewer, reviewed_at=iso(reviewed), review_note=reason, review_fields=review_fields
        )
        events.append((reviewed, reviewer, "changes_requested", reason))
    table = aws.table()
    table.put_item(Item=_ddb(item))
    for when, actor, action, note in events:
        table.put_item(
            Item={
                "pk": _pk(rid),
                "sk": f"EVENT#{iso(when)}#{uuid.uuid4().hex[:6]}",
                "at": iso(when),
                "actor": actor,
                "action": action,
                "note": note,
            }
        )
    if submitted:
        talk = [
            ("assistant", "영수증을 읽었어요. 내용이 맞는지 확인해 주세요."),
            ("user", "맞아요"),
            ("assistant", "어떤 일로 쓰신 비용인가요?"),
            ("user", fields["purpose"]),
            ("assistant", "목적과 분류를 정했어요. 마지막으로 확인해 주세요."),
        ]
        for i, (role, text) in enumerate(talk):
            at_msg = iso(created + timedelta(minutes=2 + i))
            table.put_item(
                Item={
                    "pk": _pk(rid),
                    "sk": f"MSG#{at_msg}#{uuid.uuid4().hex[:6]}",
                    "at": at_msg,
                    "role": role,
                    "text": text,
                }
            )
    jpg = receipt_image(fields, items)
    s3, bucket = aws.client("s3"), get_settings().bucket
    for prefix in ("raw", "incoming"):
        s3.put_object(Bucket=bucket, Key=f"{prefix}/{rid}.jpg", Body=jpg, ContentType="image/jpeg")
    return rid


def main() -> None:
    now = datetime.now(KST)
    employees = [k for k, v in DEV_PROFILES.items() if v[4] == "employee"]
    reviewers = [DEV_PROFILES[k][0] for k, v in DEV_PROFILES.items() if v[4] == "reviewer"]
    count: dict[str, int] = {}
    # a mix worth testing with: a few drafts, a real review queue, some sent back, most approved
    pool = ["draft"] * 5 + ["submitted"] * 9 + ["changes_requested"] * 5 + ["approved"] * 22
    rng.shuffle(pool)
    days = {"draft": (0, 3), "submitted": (0, 7), "changes_requested": (3, 20), "approved": (7, 85)}
    for n, status in enumerate(pool):
        owner = employees[n % len(employees)]
        days_ago = rng.randint(*days[status])
        at = (now - timedelta(days=days_ago)).replace(hour=rng.randint(8, 20), minute=rng.randint(0, 59))
        tweak = rng.choice([None] * 6 + ["night"])
        if status == "changes_requested" and rng.random() < 0.4:
            tweak = "mismatch"  # sent back for the wrong amounts
        put_receipt(owner, rng.choice(SHOPS), at, status, rng.choice(reviewers), now, tweak)
        count[status] = count.get(status, 0) + 1
    print("fake receipts:", sum(count.values()), count)


if __name__ == "__main__":
    main()
