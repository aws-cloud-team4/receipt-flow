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


EDGE_SIDE = 500  # the edge search is tuned for this size; keep it
PAPER_SIDE = 600  # bright-paper search and the final comparison


def _small(img: np.ndarray, side: int, interpolation: int = cv2.INTER_LINEAR) -> tuple[np.ndarray, float]:
    h, w = img.shape[:2]
    scale = side / max(h, w)
    return cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=interpolation), scale


def _edge_quad(img: np.ndarray) -> np.ndarray | None:
    """Largest four-sided outline in the edge map (original pixels). Works on plain backgrounds."""
    small, scale = _small(img, EDGE_SIDE)
    gray = cv2.GaussianBlur(cv2.cvtColor(small, cv2.COLOR_BGR2GRAY), (5, 5), 0)
    edges = cv2.dilate(cv2.Canny(gray, 50, 150), np.ones((3, 3), np.uint8))
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    area_min = gray.shape[0] * gray.shape[1] * 0.2
    for c in sorted(contours, key=cv2.contourArea, reverse=True)[:5]:
        if cv2.contourArea(c) < area_min:
            break
        approx = cv2.approxPolyDP(c, 0.02 * cv2.arcLength(c, True), True)
        if len(approx) == 4 and cv2.isContourConvex(approx):
            return _order(approx.reshape(4, 2).astype(np.float32) / scale)
    return None


def _snap(q: np.ndarray, hull: np.ndarray) -> np.ndarray:
    """Move each corner to the outline point that sticks out furthest toward it.

    A curled receipt has bowed edges, so a four-point simplification can land partway along an edge;
    the real corner is the outline point furthest out in that corner's direction.
    """
    pts = hull.reshape(-1, 2).astype(np.float32)
    center = q.mean(axis=0)
    rel = pts - center
    dist = np.linalg.norm(rel, axis=1) + 1e-6
    out = q.copy()
    for i in range(4):
        d = q[i] - center
        d /= np.linalg.norm(d) + 1e-6
        near = rel @ d / dist > 0.8  # outline points roughly in this corner's direction
        if near.any():
            out[i] = pts[near][np.argmax(rel[near] @ d)]
    return out


def _quad_from(contour: np.ndarray) -> np.ndarray | None:
    hull = cv2.convexHull(contour)
    peri = cv2.arcLength(hull, True)
    quad = None
    for eps in (0.02, 0.03, 0.045, 0.06):
        approx = cv2.approxPolyDP(hull, eps * peri, True)
        if len(approx) == 4 and cv2.isContourConvex(approx):
            quad = approx.reshape(4, 2).astype(np.float32)
            break
    if quad is None:  # the bounding rectangle, when the shape is clearly box-like
        rect = cv2.boxPoints(cv2.minAreaRect(hull)).astype(np.float32)
        if cv2.contourArea(hull) / max(1.0, cv2.contourArea(rect)) <= 0.88:
            return None
        quad = rect
    return _snap(_order(quad), hull)


def _paper_quad(small: np.ndarray) -> np.ndarray | None:
    """The receipt as the brightest colourless blob that does not touch the frame.

    Wood grain, coloured tables and shadows break the edge outline, but thermal paper stays
    bright and grey while most backgrounds are darker or coloured.
    """
    h, w = small.shape[:2]
    area = h * w
    hsv = cv2.cvtColor(cv2.GaussianBlur(small, (5, 5), 0), cv2.COLOR_BGR2HSV)
    sat, val = hsv[..., 1], hsv[..., 2]
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (7, 7))
    otsu, _ = cv2.threshold(val, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    best, best_score = None, 0.0
    for sat_max in (40, 70):
        for val_min in (otsu, np.percentile(val, 60), np.percentile(val, 75)):
            mask = ((sat < sat_max) & (val >= val_min)).astype(np.uint8) * 255
            mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=3)  # fill in the print
            mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            for c in contours:
                a = cv2.contourArea(c)
                if not area * 0.05 <= a <= area * 0.9:
                    continue
                x, y, bw, bh = cv2.boundingRect(c)
                touches = (x <= 2) + (y <= 2) + (x + bw >= w - 2) + (y + bh >= h - 2)
                if touches >= 2:  # the background, not a receipt
                    continue
                quad = _quad_from(c)
                if quad is None:
                    continue
                fill = a / max(1.0, cv2.contourArea(quad))
                if fill < 0.8:
                    continue
                score = cv2.contourArea(quad) * min(fill, 1 / fill) * (0.6 if touches else 1.0)
                if score > best_score:
                    best, best_score = quad, score
    return best


def _corners_ok(q: np.ndarray, area: float) -> bool:
    """Every corner between about 53° and 127°, not a sliver, and not just the photo's own frame."""
    if not area * 0.05 <= cv2.contourArea(q) <= area * 0.9:
        return False
    for i in range(4):
        v1, v2 = q[i - 1] - q[i], q[(i + 1) % 4] - q[i]
        if abs(float(v1 @ v2) / (np.linalg.norm(v1) * np.linalg.norm(v2) + 1e-6)) >= 0.6:
            return False
    return True


def _contrast(val: np.ndarray, q: np.ndarray) -> float:
    """How much brighter the inside is than a thin band just outside."""
    inside = np.zeros(val.shape, np.uint8)
    cv2.fillPoly(inside, [q.astype(np.int32)], 255)
    band = cv2.dilate(inside, np.ones((11, 11), np.uint8)) & ~inside
    if not inside.any() or not band.any():
        return 0.0
    return float(val[inside > 0].mean() - val[band > 0].mean())


def _nested(a: np.ndarray, b: np.ndarray) -> bool:
    """One quad lies almost entirely inside the other."""
    inter, _ = cv2.intersectConvexConvex(a, b)
    return inter >= 0.9 * min(cv2.contourArea(a), cv2.contourArea(b))


def find_corners(img: np.ndarray) -> np.ndarray | None:
    """Four corners (TL, TR, BR, BL) in original pixels, or None.

    Two searches: the edge outline and the bright-paper blob. Each answer must look like a
    rectangle seen at an angle. If both outline the same receipt the edge one is kept; otherwise
    the one that stands out most from its surroundings wins.
    """
    small, scale = _small(img, PAPER_SIDE, cv2.INTER_AREA)
    paper = _paper_quad(small)
    candidates = [_edge_quad(img), None if paper is None else paper / scale]
    val = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)[..., 2]
    area = small.shape[0] * small.shape[1]
    found = [q * scale for q in candidates if q is not None and _corners_ok(q * scale, area)]
    if len(found) == 2 and _nested(found[0], found[1]):
        # Same receipt: the edge outline is the precise one. The paper blob can stop at a shadow
        # or a printed barcode, or spill into a pale table.
        found = found[:1]
    if not found:
        return None
    return _order(max(found, key=lambda q: _contrast(val, q)) / scale)


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
