"""Render a synthetic Korean receipt (no real personal data) for demos and smoke tests.

uv run --with pillow python scripts/make_sample_receipt.py ../docs/samples/sample-receipt.jpg
"""

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FONT = "C:/Windows/Fonts/malgun.ttf" if Path("C:/Windows/Fonts/malgun.ttf").exists() else "NanumGothic.ttf"

LINES = [
    ("center", 34, "한빛 김밥천국 역삼점"),
    ("left", 22, "사업자번호: 214-86-12345"),
    ("left", 22, "대표: 홍길동   TEL 02-555-0101"),
    ("left", 22, "서울 강남구 테헤란로 123"),
    ("rule", 0, ""),
    ("left", 22, "일시: 2026-10-14 12:41"),
    ("rule", 0, ""),
    ("row", 24, ("참치김밥 x2", "9,000")),
    ("row", 24, ("라볶이 x1", "7,500")),
    ("row", 24, ("돈까스 x2", "19,000")),
    ("rule", 0, ""),
    ("row", 24, ("공급가액", "32,273")),
    ("row", 24, ("부가세", "3,227")),
    ("row", 30, ("합계", "35,500")),
    ("rule", 0, ""),
    ("left", 22, "신용카드 결제  승인번호 30012345"),
    ("left", 22, "카드번호 9410-****-****-1234"),
    ("center", 22, "감사합니다"),
]


def render(out: Path) -> None:
    w, h = 620, 980
    img = Image.new("RGB", (w, h), (250, 249, 245))
    d = ImageDraw.Draw(img)
    y = 40
    for kind, size, text in LINES:
        if kind == "rule":
            d.line((30, y + 8, w - 30, y + 8), fill=(80, 80, 80), width=2)
            y += 26
            continue
        font = ImageFont.truetype(FONT, size)
        if kind == "row":
            left, right = text
            d.text((40, y), left, font=font, fill=(20, 20, 20))
            d.text((w - 40, y), right, font=font, fill=(20, 20, 20), anchor="ra")
        elif kind == "center":
            d.text((w / 2, y), text, font=font, fill=(20, 20, 20), anchor="ma")
        else:
            d.text((40, y), text, font=font, fill=(20, 20, 20))
        y += size + 18
    # Put the paper on a dark desk, slightly rotated, like a phone photo.
    canvas = Image.new("RGB", (900, 1250), (45, 48, 55))
    canvas.paste(img.rotate(4, expand=True, fillcolor=(45, 48, 55)), (110, 90))
    out.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out, "JPEG", quality=90)
    print("wrote", out)


if __name__ == "__main__":
    render(Path(sys.argv[1] if len(sys.argv) > 1 else "sample-receipt.jpg"))
