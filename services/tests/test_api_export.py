import csv
import io

from conftest import REV
from receiptflow_common import aws, store

PROFILE = {"employee_no": "SAL2026901", "department": "영업부", "position": "대리"}


def make(status: str, when: str, total: int, **fields) -> str:
    rid = store.create_receipt("emp-1", "kim", "auto", PROFILE)["id"]
    base = {"merchant_name": "합성상점", "transaction_at": when, "total_amount": total, "category": "food"}
    store.update_receipt(rid, review_status=status, fields={"department": "영업부", **base, **fields})
    return rid


def rows(api, query: str) -> tuple[list[list[str]], str]:
    resp = api.get(f"/api/review/export.csv?{query}", headers=REV)
    assert resp.status_code == 200
    return list(csv.reader(io.StringIO(resp.text.lstrip("﻿")))), resp.headers["content-disposition"]


def test_all_is_the_default_and_skips_drafts_and_other_months(api):
    approved = make("approved", "2026-10-02 12:00", 10000)
    submitted = make("submitted", "2026-10-01 09:00", 5000)
    make("draft", "2026-10-03 09:00", 7000)
    make("approved", "2026-09-30 23:00", 3000)

    table, disposition = rows(api, "month=2026-10")
    assert [r[0] for r in table[1:]] == [submitted, approved]  # by transaction time
    assert 'filename="receipts-2026-10.csv"' in disposition


def test_approved_only_with_a_total_row(api):
    a = make("approved", "2026-10-02 12:00", 10000)
    b = make("approved", "2026-10-05 18:30", 2500)
    make("changes_requested", "2026-10-04 10:00", 9999)

    table, disposition = rows(api, "month=2026-10&status=approved")
    head, body, total = table[0], table[1:-1], table[-1]
    assert [r[0] for r in body] == [a, b]
    assert total[0] == "합계" and total[4] == "2건"
    assert total[head.index("총액")] == "12500"
    assert 'filename="receipts-2026-10-approved.csv"' in disposition


def test_unknown_status_is_rejected(api):
    assert api.get("/api/review/export.csv?month=2026-10&status=draft", headers=REV).status_code == 400


def test_text_cells_cannot_run_as_spreadsheet_formulas(api):
    make("approved", "2026-10-02 12:00", 10000, merchant_name='=HYPERLINK("x")', purpose="-1+2")

    table, _ = rows(api, "month=2026-10")
    head, row = table[0], table[1]
    assert row[head.index("상호명")] == '\'=HYPERLINK("x")'
    assert row[head.index("지출 목적")] == "'-1+2"
    assert row[head.index("총액")] == "10000"  # numbers stay numbers


def test_export_reads_every_dynamodb_page(api, monkeypatch):
    ids = {make("approved", f"2026-10-0{d} 12:00", 1000) for d in range(1, 6)}
    real = aws.table()
    query = real.query
    monkeypatch.setattr(real, "query", lambda **kwargs: query(**kwargs, Limit=1))
    assert {r["id"] for r in store.list_all_by_status("approved")} == ids
