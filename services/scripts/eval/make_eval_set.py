"""Synthetic Korean receipts with ground truth, for comparing extraction models.

    uv run --with pillow python scripts/eval/make_eval_set.py   # writes scripts/eval/set/

No real personal data: every name, number and card is made up. Each case mixes layout and
photo conditions (tilt, blur, low light, small print) that hurt real-world accuracy.
"""

import json
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

OUT = Path(__file__).with_name("set")
# Korean font: Windows 맑은 고딕, macOS Apple SD 산돌고딕, Linux 나눔고딕, else NanumGothic.ttf here.
FONTS = (
    "C:/Windows/Fonts/malgun.ttf",
    "/System/Library/Fonts/AppleSDGothicNeo.ttc",
    "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
)
FONT = next((f for f in FONTS if Path(f).exists()), "NanumGothic.ttf")

SHOPS = [
    ("한빛 김밥천국 역삼점", "214-86-12345", ["참치김밥", "라볶이", "돈까스", "쫄면"]),
    ("스타벅스 강남R점", "201-81-21515", ["아메리카노 T", "카페라떼 G", "치즈케이크"]),
    ("교보문고 광화문점", "102-81-11670", ["클라우드 아키텍처 입문", "파이썬 실무"]),
    ("GS25 선릉역점", "120-85-63021", ["삼다수 2L", "샌드위치", "커피우유"]),
    ("오피스디포 테헤란점", "211-87-90412", ["A4용지 박스", "볼펜 12입", "포스트잇"]),
    ("카카오T 택시", "120-81-47521", ["택시 요금"]),
    ("본죽&비빔밥 삼성점", "105-12-88731", ["전복죽", "불고기비빔밥", "야채죽"]),
    ("이마트 성수점", "206-85-26551", ["생수 24입", "종이컵", "일회용 접시"]),
]
PAYMENTS = ["신용카드", "체크카드", "현금"]


def build_case(i: int, rng: random.Random) -> tuple[list[tuple], dict]:
    shop, bizno, menu = SHOPS[i % len(SHOPS)]
    items = [
        (name, rng.randint(1, 3), rng.choice([1500, 3000, 4500, 6000, 7500, 9000, 12000]))
        for name in rng.sample(menu, k=min(len(menu), rng.randint(1, 3)))
    ]
    total = sum(q * p for _, q, p in items)
    supply = round(total / 1.1)
    vat = total - supply
    day = rng.randint(1, 28)
    hour, minute = rng.randint(8, 22), rng.randint(0, 59)
    when = f"2026-09-{day:02d}T{hour:02d}:{minute:02d}"
    pay = rng.choice(PAYMENTS)
    show_vat = i % 4 != 3  # some receipts print only the total
    lines = [
        ("center", 32, shop),
        ("left", 21, f"사업자번호: {bizno}"),
        ("left", 21, "TEL 02-555-0" + str(100 + i)),
        ("rule",),
        ("left", 21, f"일시: {when.replace('T', ' ')}"),
        ("rule",),
        *[("row", 23, f"{n} x{q}", f"{q * p:,}") for n, q, p in items],
        ("rule",),
    ]
    if show_vat:
        lines += [("row", 23, "공급가액", f"{supply:,}"), ("row", 23, "부가세", f"{vat:,}")]
    lines += [("row", 29, "합계", f"{total:,}"), ("rule",), ("left", 21, f"{pay} 결제")]
    issuer = card = approval = None
    if pay != "현금":
        issuer = rng.choice(["신한카드", "KB국민카드", "삼성카드"]) if pay == "신용카드" else "NH농협체크"
        card = f"{rng.randint(4000, 9999)}-****-****-{rng.randint(1000, 9999)}"
        approval = f"{rng.randint(10000000, 99999999)}"
        lines += [
            ("left", 21, f"카드사: {issuer}"),
            ("left", 21, f"카드번호 {card}"),
            ("left", 21, f"승인번호 {approval}"),
        ]
    lines.append(("center", 21, "감사합니다"))
    truth = {
        "merchant_name": shop,
        "business_number": bizno,
        "transaction_at": when,
        "supply_amount": supply if show_vat else None,
        "vat_amount": vat if show_vat else None,
        "total_amount": total,
        "payment_method": pay,
        "card_issuer": issuer,
        "card_number": card,
        "approval_number": approval,
    }
    return lines, truth


def render(lines: list[tuple], scale: float) -> Image.Image:
    w = 620
    img = Image.new("RGB", (w, 1100), (250, 249, 245))
    d = ImageDraw.Draw(img)
    y = 40
    for line in lines:
        if line[0] == "rule":
            d.line((30, y + 8, w - 30, y + 8), fill=(80, 80, 80), width=2)
            y += 26
            continue
        kind, size, *text = line
        font = ImageFont.truetype(FONT, int(size * scale))
        if kind == "row":
            d.text((40, y), text[0], font=font, fill=(20, 20, 20))
            d.text((w - 40, y), text[1], font=font, fill=(20, 20, 20), anchor="ra")
        elif kind == "center":
            d.text((w / 2, y), text[0], font=font, fill=(20, 20, 20), anchor="ma")
        else:
            d.text((40, y), text[0], font=font, fill=(20, 20, 20))
        y += int(size * scale) + 18
    return img.crop((0, 0, w, y + 40))


def photograph(paper: Image.Image, cond: str, rng: random.Random) -> Image.Image:
    angle = {"tilt": rng.choice([-9, 8, 11]), "blur": 3, "dark": -4, "small": 2}.get(cond, rng.uniform(-3, 3))
    canvas = Image.new("RGB", (paper.width + 300, paper.height + 300), (45, 48, 55))
    canvas.paste(paper.rotate(angle, expand=True, fillcolor=(45, 48, 55)), (120, 120))
    if cond == "blur":
        canvas = canvas.filter(ImageFilter.GaussianBlur(2.2))
    if cond == "dark":
        canvas = ImageEnhance.Brightness(canvas).enhance(0.45)
        canvas = ImageEnhance.Contrast(canvas).enhance(0.7)
    if cond == "small":
        canvas = canvas.resize((canvas.width // 2, canvas.height // 2))
    return canvas


CONDITIONS = ["clean", "tilt", "blur", "dark", "small"] * 2 + ["clean", "tilt"]


def main() -> None:
    rng = random.Random(20261016)
    OUT.mkdir(parents=True, exist_ok=True)
    truth = {}
    for i, cond in enumerate(CONDITIONS):
        lines, t = build_case(i, rng)
        photo = photograph(render(lines, 0.8 if cond == "small" else 1.0), cond, rng)
        name = f"r{i:02d}-{cond}.jpg"
        photo.save(OUT / name, "JPEG", quality=70 if cond == "small" else 88)
        truth[name] = t
    (OUT / "truth.json").write_text(json.dumps(truth, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {len(truth)} receipts to {OUT}")


if __name__ == "__main__":
    main()
