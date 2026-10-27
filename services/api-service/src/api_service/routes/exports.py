"""Exports HTTP endpoints. Keep existing paths and response shapes."""

import csv
import io
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from receiptflow_common import store
from receiptflow_common.auth import User, reviewer_only
from receiptflow_common.domain import (
    ALL_FIELDS,
    AMOUNT_FIELDS,
    CATEGORIES,
    FIELD_LABELS,
    REVIEW_LABELS,
    REVIEW_STATUSES,
)

router = APIRouter()

# Spreadsheet apps run a cell starting with one of these as a formula (CSV injection).
FORMULA_START = ("=", "+", "-", "@", "\t", "\r", "\n")


def _cell(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, str) and value.startswith(FORMULA_START):
        return "'" + value
    return value


@router.get("/api/review/export.csv")
def export_csv(
    month: str = Query(pattern=r"^\d{4}-\d{2}$"),
    status: Literal["all", "approved"] = "all",
    _: User = Depends(reviewer_only),
) -> Response:
    statuses = ("approved",) if status == "approved" else [s for s in REVIEW_STATUSES if s != "draft"]
    rows = [
        r
        for s in statuses
        for r in store.list_all_by_status(s)
        if str(r.get("fields", {}).get("transaction_at") or "").startswith(month)
    ]
    rows.sort(key=lambda r: r["fields"].get("transaction_at") or "")
    buf = io.StringIO()
    writer = csv.writer(buf)
    head = ["증빙 ID", "사번", "제출자", "직급", "상태", *(FIELD_LABELS[k] for k in ALL_FIELDS)]
    writer.writerow([*head, "제출일시", "검수자", "검수일시", "보완 요청 사유"])
    for r in rows:
        owner = r.get("owner_profile") or {}
        values = [
            CATEGORIES.get(v, v) if k == "category" else v
            for k, v in ((k, r["fields"].get(k)) for k in ALL_FIELDS)
        ]
        writer.writerow(
            _cell(v)
            for v in [
                r["id"],
                owner.get("employee_no"),
                r["owner_name"],
                owner.get("position"),
                REVIEW_LABELS[r["review_status"]],
                *values,
                (r.get("submitted_at") or "")[:16],
                r.get("reviewed_by"),
                (r.get("reviewed_at") or "")[:16],
                r.get("review_note") if r["review_status"] == "changes_requested" else None,
            ]
        )
    if status == "approved":
        sums = {k: sum(r["fields"].get(k) or 0 for r in rows) for k in AMOUNT_FIELDS}
        writer.writerow(["합계", "", "", "", f"{len(rows)}건", *(sums.get(k, "") for k in ALL_FIELDS)])
    name = f"receipts-{month}-approved.csv" if status == "approved" else f"receipts-{month}.csv"
    return Response(
        "﻿" + buf.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )
