"""Review HTTP endpoints. Keep existing paths and response shapes."""

from typing import Any, Literal

from fastapi import APIRouter, Depends
from receiptflow_common.auth import User, reviewer_only

from api_service import receipt_workflows as workflows
from api_service.schemas import ChangeRequest

router = APIRouter()


@router.get("/api/review/receipts")
def review_list(
    status: Literal["submitted", "approved", "changes_requested", "draft"] = "submitted",
    _: User = Depends(reviewer_only),
) -> dict[str, Any]:
    return workflows.review_list(status=status, _=_)


@router.post("/api/review/receipts/{receipt_id}/approve")
def approve(receipt_id: str, user: User = Depends(reviewer_only)) -> dict[str, Any]:
    return workflows.approve(receipt_id=receipt_id, user=user)


@router.post("/api/review/receipts/{receipt_id}/request-changes")
def request_changes(
    receipt_id: str, body: ChangeRequest, user: User = Depends(reviewer_only)
) -> dict[str, Any]:
    return workflows.request_changes(receipt_id=receipt_id, body=body, user=user)
