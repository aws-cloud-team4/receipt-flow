import cv2
import numpy as np
from preprocess_service.correct import correct


def test_finds_and_flattens_a_tilted_receipt():
    canvas = np.full((1200, 900, 3), 40, np.uint8)
    paper = np.array([[250, 150], [700, 220], [640, 1050], [190, 980]], np.int32)
    cv2.fillPoly(canvas, [paper], (245, 245, 245))
    ok, buf = cv2.imencode(".jpg", canvas)
    assert ok

    result = correct(buf.tobytes())

    assert result.corners is not None
    tl, tr, br, bl = result.corners
    assert abs(tl[0] - 250) < 15 and abs(br[1] - 1050) < 15
    assert result.height > result.width  # portrait receipt


def test_tall_receipt_keeps_enough_width_for_small_text():
    from preprocess_service.correct import MAX_SIDE, apply

    tall = np.full((4000, 1400, 3), 245, np.uint8)  # a long receipt photographed whole
    ok, buf = cv2.imencode(".jpg", tall)
    out = apply(buf.tobytes(), None)
    assert max(out.width, out.height) == MAX_SIDE == 2400 and out.width >= 800


def _photo(background: np.ndarray, paper: np.ndarray, curl: float = 0.0) -> np.ndarray:
    """A white receipt with printed lines laid on `background`; `curl` bows its long edges."""
    h, w = background.shape[:2]
    sheet = np.full((1400, 520, 3), 238, np.uint8)
    for y in range(80, 1340, 34):  # print, so the paper is not one flat blob
        cv2.line(sheet, (40, y), (40 + (y * 37) % 400, y), (40, 40, 40), 6)
    if curl:
        yy, xx = np.mgrid[0:1400, 0:520].astype(np.float32)
        bow = curl * np.sin(yy / 1400 * np.pi)  # both long edges bulge out at the middle
        xs = (xx - 260) / (1 + 2 * bow / 520) + 260
        sheet = cv2.remap(sheet, xs, yy, cv2.INTER_LINEAR, borderValue=(0, 0, 0))
        inside = cv2.remap(np.full((1400, 520), 255, np.uint8), xs, yy, cv2.INTER_NEAREST, borderValue=0)
    else:
        inside = np.full((1400, 520), 255, np.uint8)
    m = cv2.getPerspectiveTransform(
        np.float32([[0, 0], [520, 0], [520, 1400], [0, 1400]]), paper.astype(np.float32)
    )
    warped = cv2.warpPerspective(sheet, m, (w, h))
    mask = cv2.warpPerspective(inside, m, (w, h)) > 0
    return np.where(mask[..., None], warped, background)


def _wood(h: int, w: int, base: tuple[int, int, int]) -> np.ndarray:
    y, x = np.mgrid[0:h, 0:w]
    grain = (np.sin(x / 7.0 + np.sin(y / 50.0) * 4) * 28 + np.sin(x / 2.3) * 8)[..., None]
    return (np.array(base, np.float32) + grain).clip(0, 255).astype(np.uint8)


PAPER = np.array([[330, 260], [800, 300], [720, 1640], [250, 1600]], np.float32)  # TL, TR, BR, BL


def _close(found, expected, tol: float) -> bool:
    return found is not None and float(np.abs(found - expected).max()) < tol


def test_finds_receipt_on_wood_grain():
    from preprocess_service.correct import find_corners

    img = _photo(_wood(1900, 1100, (40, 90, 150)), PAPER)  # orange-brown table
    assert _close(find_corners(img), PAPER, 25)


def test_finds_receipt_on_coloured_table():
    from preprocess_service.correct import find_corners

    yellow = np.full((1900, 1100, 3), (60, 190, 225), np.uint8)
    img = _photo(yellow, PAPER).astype(np.float32)
    img[700:1100] *= 0.8  # a hand's shadow across the table and half the receipt
    assert _close(find_corners(img.astype(np.uint8)), PAPER, 25)


def test_curled_receipt_keeps_its_real_corners():
    from preprocess_service.correct import find_corners

    img = _photo(_wood(1900, 1100, (35, 35, 35)), PAPER, curl=45)  # dark table, bowed edges
    assert _close(find_corners(img), PAPER, 30)


def test_background_alone_has_no_receipt():
    from preprocess_service.correct import find_corners

    assert find_corners(_wood(1900, 1100, (40, 90, 150))) is None
