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
