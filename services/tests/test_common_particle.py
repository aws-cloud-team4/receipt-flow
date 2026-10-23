from receiptflow_common.domain import ro


def test_ro_follows_the_last_sound():
    assert ro("구매") == "로" and ro("식사·간식비") == "로" and ro("서울") == "로"  # vowel, ㄹ
    assert ro("점심") == "으로" and ro("접대·선물비 확인") == "으로"
    assert ro("(비움)") == "으로" and ro("'회의 다과'") == "로"  # brackets and quotes skipped
    assert ro("2,800") == "으로" and ro("2026-10-14 12:57") == "로" and ro("12:51") == "로"
    assert ro("KTX") == "(으)로"
