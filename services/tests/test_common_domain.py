from receiptflow_common.domain import duplicate_key, missing_required, normalize_fields, run_checks


def codes(fields, dup=None):
    return {c["code"] for c in run_checks(fields, dup)}


def test_amounts_are_coerced():
    f = normalize_fields(
        {"total_amount": "13,500원", "vat_amount": 1227, "merchant_name": "  카페  ", "x": 1}
    )
    assert f == {"total_amount": 13500, "vat_amount": 1227, "merchant_name": "카페"}


def test_amount_check_only_when_all_three_present():
    assert "amount_mismatch" not in codes({"total_amount": 100, "vat_amount": 10})
    assert "amount_mismatch" not in codes({"supply_amount": 90, "vat_amount": 10, "total_amount": 100})
    assert "amount_mismatch" in codes({"supply_amount": 90, "vat_amount": 10, "total_amount": 110})


def test_time_based_flags():
    assert codes({"transaction_at": "2026-10-14T23:10"}) == {"late_night"}
    assert codes({"transaction_at": "2026-10-17"}) == {"weekend"}  # Saturday
    assert codes({"transaction_at": "2026-10-14"}) == set()
    assert codes({"transaction_at": "14/10/2026"}) == {"bad_date"}


def test_duplicate_flag_and_key():
    assert duplicate_key(
        {"merchant_name": "스타 벅스", "transaction_at": "2026-10-14T12:00", "total_amount": 5}
    ) == ("스타벅스|2026-10-14|5")
    assert "duplicate" in codes({}, "abc")


def test_missing_required():
    assert missing_required({"merchant_name": "a", "transaction_at": "2026-10-14", "total_amount": 0}) == [
        "category",
        "purpose",
    ]


def test_category_accepts_code_or_label():
    from receiptflow_common.domain import to_category

    assert to_category("food") == "food" and to_category("식사·간식비") == "food"
    assert to_category("도서·교육비") == "education"
    assert to_category("간식") is None and to_category("") is None


def test_card_number_is_kept_exactly_as_printed():
    from receiptflow_common.domain import card_number_as_printed

    assert card_number_as_printed("9430-1178-****-558*") == "9430-1178-****-558*"  # masked as printed
    assert card_number_as_printed("94909401") == "94909401"  # only part printed
    assert card_number_as_printed("5327-50**-****-****") == "5327-50**-****-****"
    assert card_number_as_printed("  4518 42**  ****  1234 ") == "4518 42** **** 1234"
    assert card_number_as_printed("") is None
    assert normalize_fields({"card_number": "9430-1178-****-558*"})["card_number"] == "9430-1178-****-558*"


def test_categories_v3_and_old_codes():
    from receiptflow_common.domain import CATEGORIES, to_category

    assert len(CATEGORIES) == 10 and CATEGORIES["welfare_event"] == "행사·복리후생비"
    # codes and labels saved before the revision still map to the new list
    assert [to_category(c) for c in ("meal", "team_dinner", "meeting")] == ["food"] * 3
    assert to_category("transport") == "travel" and to_category("postage") == "delivery"
    assert to_category("회식비") == "food" and to_category("소모품비") == "supplies"


def test_amount_check_counts_the_tax_exempt_part():
    from receiptflow_common.domain import run_checks

    mart = {"supply_amount": 20782, "vat_amount": 2078, "exempt_amount": 10880, "total_amount": 33740}
    assert not [c for c in run_checks(mart) if c["code"] == "amount_mismatch"]
    wrong = {**mart, "exempt_amount": None}
    msg = next(c["message"] for c in run_checks(wrong) if c["code"] == "amount_mismatch")
    assert "22,860" in msg
    books = {"supply_amount": None, "vat_amount": None, "exempt_amount": 59000, "total_amount": 59000}
    assert not [c for c in run_checks(books) if c["code"] == "amount_mismatch"]


def test_transaction_time_keeps_minutes_only():
    assert normalize_fields({"transaction_at": "2026-10-14T12:57:59"})["transaction_at"] == "2026-10-14T12:57"
    assert normalize_fields({"transaction_at": "2026-10-14 12:57"})["transaction_at"] == "2026-10-14T12:57"
    assert normalize_fields({"transaction_at": "2026-10-14"})["transaction_at"] == "2026-10-14"
