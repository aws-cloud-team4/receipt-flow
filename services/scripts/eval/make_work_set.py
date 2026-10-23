"""Synthetic card-payment receipts for everyday work expenses, with ground truth.

    uv run --with pillow python scripts/eval/make_work_set.py   # writes scripts/eval/work/
    uv run python scripts/eval/compare_models.py --set work global.anthropic.claude-sonnet-5-5

Real samples lean towards food and marts; this set covers the rest of what employees pay for
(fuel, taxi, parking, train, hotel, stationery, courier, post, books, seminars, printing) and
mixes in the traps seen in real receipts: tax-exempt amounts, a final amount after a discount,
a store code after the name, a print time after the approval time, a business number without
hyphens, a check card under a "신용카드" header, partial card numbers, approval numbers with a
leading zero. Every name and number is made up.
"""

import json
import random
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

OUT = Path(__file__).with_name("work")
FONT = "C:/Windows/Fonts/malgun.ttf" if Path("C:/Windows/Fonts/malgun.ttf").exists() else "NanumGothic.ttf"


@dataclass
class Case:
    shop: str  # what the merchant_name truth is
    printed_shop: str  # what is printed (may carry a store code)
    bizno: str
    kind: str
    items: list[tuple[str, int, int]]  # (name, qty, price) — price is per unit
    hour: tuple[int, int] = (9, 19)
    exempt: bool = False  # all items tax-exempt (books, post)
    exempt_items: int = 0  # the last N items are tax-exempt (marts)
    discount: int = 0
    extra: list[tuple] = field(default_factory=list)  # lines printed before the totals


CASES = [
    Case(
        "SK에너지 역삼주유소",
        "SK에너지 역삼주유소",
        "220-81-55021",
        "fuel",
        [("휘발유 31.348L", 1, 50000)],
        (7, 9),
    ),
    Case(
        "카카오T 블루",
        "카카오T 블루",
        "120-81-47521",
        "taxi",
        [("택시 요금 (강남역→여의도)", 1, 23400)],
        (8, 23),
    ),
    Case(
        "강남 공영주차장",
        "강남 공영주차장",
        "211-83-00412",
        "parking",
        [("주차요금 2시간 10분", 1, 7800)],
        (10, 20),
        extra=[("left", 20, "입차 {in_time}"), ("left", 20, "출차 {when}")],
    ),
    Case(
        "코레일 서울역",
        "코레일 서울역",
        "314-82-10024",
        "train",
        [("KTX 서울→부산 일반실", 1, 59800)],
        (6, 10),
        extra=[("left", 20, "승차일 {ride_date} 07:30 출발")],
    ),
    Case(
        "호텔 해운대 비치",
        "호텔 해운대 비치",
        "617-86-30117",
        "hotel",
        [("디럭스 더블 1박", 2, 98000)],
        (11, 15),
        extra=[("left", 20, "체크인 {ride_date} / 체크아웃 2박")],
    ),
    Case(
        "알파문구 역삼점",
        "알파문구 역삼점",
        "211-14-35720",
        "stationery",
        [("A4 복사용지 500매", 2, 6500), ("제트스트림 볼펜 0.5", 6, 1800), ("보드마카 4색", 1, 5400)],
    ),
    Case(
        "(주)아성다이소_역삼2호점",
        "(주)아성다이소_역삼2호점",
        "213-81-52063",
        "daiso",
        [("파일 홀더 A4", 4, 1000), ("멀티탭 3구 1.5m", 1, 5000), ("종이컵 50입", 2, 1000)],
    ),
    Case(
        "CJ대한통운 역삼대리점",
        "CJ대한통운 역삼대리점",
        "110-81-05034",
        "courier",
        [("택배 소형 (서울→대전)", 3, 4500)],
    ),
    Case(
        "서울역삼우체국",
        "서울역삼우체국",
        "101-83-02925",
        "post",
        [("등기우편 (통상)", 2, 2780), ("우편봉투 대", 2, 200)],
        exempt=True,
    ),
    Case(
        "교보문고 광화문점",
        "교보문고 광화문점",
        "102-81-11670",
        "books",
        [("클라우드 아키텍처 입문", 1, 32000), ("실무 SQL", 1, 27000)],
        exempt=True,
    ),
    Case(
        "이마트 성수점",
        "이마트 성수점",
        "206-85-26551",
        "mart",
        [
            ("생수 2L x6", 2, 4980),
            ("종이컵 1000입", 1, 12900),
            ("바나나 1송이", 1, 3980),
            ("귤 1kg", 1, 6900),
        ],
        exempt_items=2,
    ),
    Case(
        "스타벅스 강남R점",
        "스타벅스 강남R점 #53385",
        "201-81-21515",
        "cafe",
        [("아메리카노 T", 4, 4700), ("카페라떼 T", 2, 5200), ("치즈케이크", 1, 6500)],
        (13, 16),
    ),
    Case(
        "한우마을 역삼본점",
        "한우마을 역삼본점",
        "2148612399",
        "dinner",
        [("한우 등심 150g", 6, 39000), ("된장찌개", 2, 4000), ("맥주", 6, 5000)],
        (19, 22),
        discount=20000,
    ),
    Case(
        "GS25 선릉역점",
        "GS25 선릉역점",
        "120-85-63021",
        "convenience",
        [("삼다수 2L", 3, 1500), ("샌드위치", 2, 3900), ("커피우유", 2, 1600)],
    ),
    Case(
        "한국생산성본부",
        "한국생산성본부",
        "101-82-07012",
        "seminar",
        [("AWS 클라우드 실무 과정 수강료", 1, 330000)],
    ),
    Case(
        "킨코스 강남점",
        "킨코스 강남점",
        "220-86-71005",
        "printing",
        [("컬러 출력 A4", 120, 300), ("제본 (스프링)", 4, 3000)],
    ),
    Case(
        "온누리약국",
        "온누리약국",
        "510-05-87533",
        "pharmacy",
        [("타이레놀 500mg", 1, 3500), ("밴드 혼합형", 2, 2000)],
    ),
    Case(
        "한국도로공사 서울TG",
        "한국도로공사 서울TG",
        "202-82-01214",
        "toll",
        [("통행료 (서울→대전)", 1, 8400)],
        (6, 21),
    ),
]

ISSUERS = [
    ("신한카드", "신용카드"),
    ("KB국민체크", "체크카드"),
    ("삼성카드", "신용카드"),
    ("NH농협체크", "체크카드"),
    ("현대카드", "신용카드"),
    ("하나카드-체크", "체크카드"),
]


def build_case(i: int, c: Case, rng: random.Random) -> tuple[list[tuple], dict]:
    gross = sum(q * p for _, q, p in c.items)
    exempt_total = gross if c.exempt else sum(q * p for _, q, p in c.items[len(c.items) - c.exempt_items :])
    taxable = gross - exempt_total - c.discount
    total = gross - c.discount
    supply = round(taxable / 1.1)
    vat = taxable - supply
    day = rng.randint(1, 28)
    hour, minute = rng.randint(*c.hour), rng.randint(0, 59)
    when = f"2026-09-{day:02d}T{hour:02d}:{minute:02d}"
    printed_at = f"2026-09-{day:02d} {hour:02d}:{min(minute + 3, 59):02d}"  # reprint/print time, a bit later
    issuer, pay = ISSUERS[i % len(ISSUERS)]
    # Card numbers as receipts print them: masked middle, partial (first 8 only) or only last digits.
    style = i % 3
    if style == 0:
        card = f"{rng.randint(4000, 9999)}-{rng.randint(10, 99)}**-****-{rng.randint(100, 999)}*"
    elif style == 1:
        card = f"{rng.randint(40000000, 99999999)}"
    else:
        card = f"{rng.randint(400000, 999999)}******{rng.randint(1000, 9999)}"
    approval = f"0{rng.randint(1000000, 9999999)}" if i % 4 == 0 else f"{rng.randint(10000000, 99999999)}"
    names = {
        "in_time": f"{hour - 2:02d}:{minute:02d}",
        "when": when.replace("T", " "),
        "ride_date": when[:10],
    }

    header = "신용카드 매출전표" if i % 5 == 0 else "카드 영수증"  # header says 신용카드 even for check cards
    lines = [
        ("center", 30, c.printed_shop),
        ("left", 20, f"사업자번호 {c.bizno}" if "-" in c.bizno else f"{c.bizno}  대표 홍길동"),
        ("left", 20, "TEL 02-555-01" + f"{i:02d}"),
        ("center", 22, f"[{header}]"),
        ("rule",),
        ("left", 20, f"거래일시 {when.replace('T', ' ')}"),
        *[(k, s, t.format(**names)) for k, s, t in c.extra],
        ("rule",),
        *[("row", 22, f"{n} x{q}" if q > 1 else n, f"{q * p:,}") for n, q, p in c.items],
        ("rule",),
    ]
    if c.discount:
        lines += [("row", 22, "합계", f"{gross:,}"), ("row", 22, "쿠폰 할인", f"-{c.discount:,}")]
    if exempt_total and not c.exempt:
        lines += [("row", 22, "면세물품가액", f"{exempt_total:,}")]
    if c.exempt:
        lines += [("row", 22, "면세", f"{exempt_total:,}")]
    else:
        lines += [("row", 22, "과세물품가액", f"{supply:,}"), ("row", 22, "부가세", f"{vat:,}")]
    lines += [
        ("row", 28, "결제금액" if c.discount else "합계", f"{total:,}"),
        ("rule",),
        ("left", 20, f"카드종류 {issuer}"),
        ("left", 20, f"카드번호 {card}"),
        ("left", 20, f"승인번호 {approval}   일시불"),
        ("left", 18, f"거래번호 {rng.randint(100000, 999999)}-{rng.randint(1000, 9999)}"),
        ("left", 18, f"출력일시 {printed_at}"),
        ("center", 20, "감사합니다"),
    ]
    truth = {
        "merchant_name": c.shop,
        "business_number": c.bizno if "-" in c.bizno else f"{c.bizno[:3]}-{c.bizno[3:5]}-{c.bizno[5:]}",
        "transaction_at": when,
        "supply_amount": None if c.exempt else supply,
        "vat_amount": None if c.exempt else vat,
        "exempt_amount": exempt_total or None,
        "total_amount": total,
        "payment_method": pay,
        "card_issuer": issuer,
        "card_number": card,
        "approval_number": approval,
        "kind": c.kind,
    }
    return lines, truth


def render(lines: list[tuple]) -> Image.Image:
    w = 640
    img = Image.new("RGB", (w, 1400), (250, 249, 245))
    d = ImageDraw.Draw(img)
    y = 40
    for line in lines:
        if line[0] == "rule":
            d.line((30, y + 8, w - 30, y + 8), fill=(80, 80, 80), width=2)
            y += 26
            continue
        kind, size, *text = line
        font = ImageFont.truetype(FONT, size)
        if kind == "row":
            d.text((40, y), text[0], font=font, fill=(20, 20, 20))
            d.text((w - 40, y), text[1], font=font, fill=(20, 20, 20), anchor="ra")
        elif kind == "center":
            d.text((w / 2, y), text[0], font=font, fill=(20, 20, 20), anchor="ma")
        else:
            d.text((40, y), text[0], font=font, fill=(20, 20, 20))
        y += size + 16
    return img.crop((0, 0, w, y + 40))


def photograph(paper: Image.Image, cond: str, rng: random.Random) -> Image.Image:
    angle = {"tilt": rng.choice([-8, 7, 10]), "blur": 2}.get(cond, rng.uniform(-2, 2))
    canvas = Image.new("RGB", (paper.width + 260, paper.height + 260), (45, 48, 55))
    canvas.paste(paper.rotate(angle, expand=True, fillcolor=(45, 48, 55)), (110, 110))
    if cond == "blur":
        canvas = canvas.filter(ImageFilter.GaussianBlur(1.6))
    if cond == "dark":
        canvas = ImageEnhance.Contrast(ImageEnhance.Brightness(canvas).enhance(0.55)).enhance(0.75)
    return canvas


CONDITIONS = ["clean", "tilt", "blur", "dark"]


def main() -> None:
    rng = random.Random(20261016)
    OUT.mkdir(parents=True, exist_ok=True)
    truth = {}
    for i, c in enumerate(CASES):
        cond = CONDITIONS[i % len(CONDITIONS)]
        lines, t = build_case(i, c, rng)
        name = f"w{i:02d}-{c.kind}-{cond}.jpg"
        photograph(render(lines), cond, rng).save(OUT / name, "JPEG", quality=88)
        truth[name] = t
    (OUT / "truth.json").write_text(json.dumps(truth, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {len(truth)} receipts to {OUT}")


if __name__ == "__main__":
    main()
