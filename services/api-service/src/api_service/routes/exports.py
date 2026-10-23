"""Exports HTTP endpoints. Keep existing paths and response shapes."""

import csv
import io

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from receiptflow_common import store
from receiptflow_common.auth import User, reviewer_only
from receiptflow_common.domain import (
    ALL_FIELDS,
    CATEGORIES,
    FIELD_LABELS,
    REVIEW_LABELS,
    REVIEW_STATUSES,
)

router = APIRouter()


@router.get("/api/review/export.csv")
def export_csv(month: str = Query(pattern=r"^\d{4}-\d{2}$"), _: User = Depends(reviewer_only)) -> Response:
    rows = [
        r
        for status in REVIEW_STATUSES
        if status != "draft"
        for r in store.list_by_status(status, limit=1000)
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
            [
                r["id"],
                owner.get("employee_no") or "",
                r["owner_name"],
                owner.get("position") or "",
                REVIEW_LABELS[r["review_status"]],
                *(v if v is not None else "" for v in values),
                (r.get("submitted_at") or "")[:16],
                r.get("reviewed_by") or "",
                (r.get("reviewed_at") or "")[:16],
                r.get("review_note") or "" if r["review_status"] == "changes_requested" else "",
            ]
        )
    return Response(
        "﻿" + buf.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="receipts-{month}.csv"'},
    )
