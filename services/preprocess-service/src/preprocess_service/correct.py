"""Receipt photo correction in two steps, so a person can fix the outline in between:

1. detect(): find the receipt's four corners on the original and score blur.
2. apply(): warp the (possibly user-adjusted) corners flat and encode the image the AI reads.
"""

from dataclasses import dataclass

import cv2
import numpy as np

MAX_SIDE = 2400  # long side of the corrected image (shown to people and sent to the model)
JPEG_QUALITY = 92  # small receipt text survives; the model downsizes large images itself
BLUR_SIDE = 1000  # blur is scored at a fixed size so the threshold does not depend on resolution
BLUR_MIN = 60.0  # below this the text is usually too soft to read reliably

Quad = list[list[float]]  # TL, TR, BR, BL in original-image pixels


@dataclass
class Detection:
    corners: Quad | None
    width: int
    height: int
    blur_score: float

    @property
    def blurry(self) -> bool:
        return self.blur_score < BLUR_MIN


@dataclass
class Result:
    jpeg: bytes
    corners: Quad | None
    blur_score: float
    width: int
    height: int


def decode(data: bytes) -> np.ndarray:
    img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("이미지를 읽을 수 없습니다.")
    return img


def _order(pts: np.ndarray) -> np.ndarray:
    s = pts.sum(axis=1)
    d = np.diff(pts, axis=1).ravel()
    return np.array(
        [pts[np.argmin(s)], pts[np.argmin(d)], pts[np.argmax(s)], pts[np.argmax(d)]], dtype=np.float32
    )


def find_corners(img: np.ndarray) -> np.ndarray | None:
    h, w = img.shape[:2]
    scale = 500 / max(h, w)
    small = cv2.resize(img, (int(w * scale), int(h * scale)))
    gray = cv2.GaussianBlur(cv2.cvtColor(small, cv2.COLOR_BGR2GRAY), (5, 5), 0)
    edges = cv2.dilate(cv2.Canny(gray, 50, 150), np.ones((3, 3), np.uint8))
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    area_min = small.shape[0] * small.shape[1] * 0.2
    for c in sorted(contours, key=cv2.contourArea, reverse=True)[:5]:
        if cv2.contourArea(c) < area_min:
            break
        approx = cv2.approxPolyDP(c, 0.02 * cv2.arcLength(c, True), True)
        if len(approx) == 4 and cv2.isContourConvex(approx):
            return _order(approx.reshape(4, 2).astype(np.float32) / scale)
    return None


def blur_score(img: np.ndarray) -> float:
    h, w = img.shape[:2]
    f = BLUR_SIDE / max(h, w)
    small = cv2.resize(img, (max(1, int(w * f)), max(1, int(h * f))), interpolation=cv2.INTER_AREA)
    return float(cv2.Laplacian(cv2.cvtColor(small, cv2.COLOR_BGR2GRAY), cv2.CV_64F).var())


def warp(img: np.ndarray, corners: np.ndarray) -> np.ndarray:
    tl, tr, br, bl = corners
    width = int(max(np.linalg.norm(br - bl), np.linalg.norm(tr - tl)))
    height = int(max(np.linalg.norm(tr - br), np.linalg.norm(tl - bl)))
    dst = np.array([[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]], dtype=np.float32)
    m = cv2.getPerspectiveTransform(corners, dst)
    return cv2.warpPerspective(img, m, (width, height), flags=cv2.INTER_CUBIC)  # sharper small text


def check_quad(corners: Quad, width: int, height: int) -> np.ndarray:
    """Clamp a client-sent quad into the image, order it, and reject degenerate shapes."""
    if len(corners) != 4 or any(len(p) != 2 for p in corners):
        raise ValueError("모서리는 네 점이어야 합니다.")
    pts = np.array(corners, dtype=np.float32)
    pts[:, 0] = pts[:, 0].clip(0, width - 1)
    pts[:, 1] = pts[:, 1].clip(0, height - 1)
    pts = _order(pts)
    if not cv2.isContourConvex(pts.reshape(4, 1, 2)) or cv2.contourArea(pts) < width * height * 0.05:
        raise ValueError("영수증 영역이 너무 작거나 모양이 올바르지 않습니다. 모서리를 다시 맞춰 주세요.")
    return pts


def detect(data: bytes) -> Detection:
    img = decode(data)
    corners = find_corners(img)
    h, w = img.shape[:2]
    return Detection(corners.tolist() if corners is not None else None, w, h, blur_score(img))


def apply(data: bytes, corners: Quad | None) -> Result:
    """Warp the given quad flat (None keeps the whole photo), cap the size, score blur, encode."""
    img = decode(data)
    h, w = img.shape[:2]
    quad = check_quad(corners, w, h) if corners is not None else None
    out = warp(img, quad) if quad is not None else img
    oh, ow = out.shape[:2]
    if max(oh, ow) > MAX_SIDE:
        f = MAX_SIDE / max(oh, ow)
        out = cv2.resize(out, (int(ow * f), int(oh * f)), interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", out, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
    if not ok:
        raise ValueError("이미지를 저장할 수 없습니다.")
    return Result(
        buf.tobytes(),
        quad.tolist() if quad is not None else None,
        blur_score(out),
        out.shape[1],
        out.shape[0],
    )


def correct(data: bytes) -> Result:
    """Detect and apply in one go (no human in between)."""
    found = detect(data)
    return apply(data, found.corners)
