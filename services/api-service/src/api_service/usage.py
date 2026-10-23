"""Public team AWS usage for the landing page: one snapshot a day, taken at 09:00 KST.

The organization blocks Cost Explorer, so the figure comes from AWS Budgets (refreshed by AWS a few
times a day). The first request after 09:00 reads the budget once and stores the snapshot in DynamoDB,
so every server shows the same number all day and AWS is asked at most once a day.
"""

import logging
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from fastapi import APIRouter
from receiptflow_common import aws, store
from receiptflow_common.config import get_settings
from receiptflow_common.errors import ApiError
from receiptflow_common.org import KST

log = logging.getLogger("api-service.usage")
router = APIRouter()
SNAPSHOT_AT = time(9, 0)  # KST


def snapshot_day(now: datetime) -> date:
    """The day whose 09:00 snapshot is current: today after 09:00, otherwise yesterday."""
    local = now.astimezone(KST)
    return local.date() if local.time() >= SNAPSHOT_AT else local.date() - timedelta(days=1)


def read_budget() -> dict[str, Any]:
    """Actual spend and period of the team budget (AWS Budgets)."""
    s = get_settings()
    account = aws.client("sts").get_caller_identity()["Account"]
    budget = aws.client("budgets").describe_budget(AccountId=account, BudgetName=s.usage_budget)["Budget"]
    spent = float(budget.get("CalculatedSpend", {}).get("ActualSpend", {}).get("Amount", 0))
    period = budget.get("TimePeriod", {})
    return {
        "spent": round(spent, 2),
        "limit": round(float(budget["BudgetLimit"]["Amount"]), 2),
        # the budget's dates are set in UTC (infra/terraform/ops), so read them as UTC dates
        "start": period["Start"].astimezone(UTC).date().isoformat() if period.get("Start") else None,
        "end": period["End"].astimezone(UTC).date().isoformat() if period.get("End") else None,
    }


@router.get("/api/public/usage")
def public_usage() -> dict[str, Any]:
    now = datetime.now(KST)
    day = snapshot_day(now)
    snap = store.get_usage(day.isoformat())
    if snap is None:
        try:
            snap = read_budget()
        except Exception as exc:  # no permission, no budget, AWS down: the page just hides the card
            log.warning("usage snapshot unavailable: %s", exc)
            raise ApiError(503, "usage_unavailable", "사용량을 불러올 수 없어요.") from exc
        snap["as_of"] = datetime.combine(day, SNAPSHOT_AT, KST).isoformat()
        store.put_usage(day.isoformat(), snap)
    spent, limit = snap["spent"], snap["limit"]
    end = date.fromisoformat(snap["end"]) if snap.get("end") else None
    return {
        "label": get_settings().usage_label,
        **snap,
        "remaining": round(max(limit - spent, 0), 2),
        "percent": round(spent / limit * 100, 1) if limit else 0,
        "currency": "USD",
        "days_left": max((end - now.date()).days, 0) if end else None,
    }
