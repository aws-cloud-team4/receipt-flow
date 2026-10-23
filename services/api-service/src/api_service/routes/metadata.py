"""Metadata HTTP endpoints. Keep existing paths and response shapes."""

from typing import Any

from fastapi import APIRouter, Depends
from receiptflow_common import org
from receiptflow_common.auth import User, current_user
from receiptflow_common.domain import CATEGORIES, CATEGORY_HINTS, FIELD_LABELS

router = APIRouter()


@router.get("/api/me")
def me(user: User = Depends(current_user)) -> dict[str, Any]:
    return user.profile()


@router.get("/api/meta")
def meta(_: User = Depends(current_user)) -> dict[str, Any]:
    """Fixed lists the web shows as choices (categories, departments) and field labels."""
    return {
        "departments": [{"code": c, "name": n} for c, n, _ in org.DEPARTMENTS],
        "categories": [
            {"code": c, "label": label, "hint": CATEGORY_HINTS[c]} for c, label in CATEGORIES.items()
        ],
        "field_labels": FIELD_LABELS,
    }
