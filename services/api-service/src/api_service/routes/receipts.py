"""Receipt HTTP endpoints with employee-only writing and reviewer reading."""

from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from receiptflow_common.auth import User, current_user, employee_only

from api_service import receipt_workflows as workflows
from api_service.schemas import PatchReceipt

router = APIRouter()


@router.post("/api/receipts", status_code=201)
def create_receipt(user: User = Depends(employee_only)) -> dict[str, Any]:
    return workflows.create_receipt(user=user)


@router.post("/api/receipts/{receipt_id}/upload-url")
def reupload(receipt_id: str, user: User = Depends(employee_only)) -> dict[str, Any]:
    return workflows.reupload(receipt_id=receipt_id, user=user)


@router.post("/api/receipts/{receipt_id}/uploaded")
def uploaded(receipt_id: str, user: User = Depends(employee_only)) -> dict[str, Any]:
    """Called after preprocess-service wrote the cropped image."""
    return workflows.uploaded(receipt_id=receipt_id, user=user)


@router.get("/api/receipts")
def my_receipts(user: User = Depends(employee_only)) -> dict[str, Any]:
    return workflows.my_receipts(user=user)


@router.get("/api/receipts/{receipt_id}")
def get_receipt(receipt_id: str, user: User = Depends(current_user)) -> dict[str, Any]:
    return workflows.get_receipt(receipt_id=receipt_id, user=user)


@router.patch("/api/receipts/{receipt_id}")
def patch_receipt(receipt_id: str, body: PatchReceipt, user: User = Depends(employee_only)) -> dict[str, Any]:
    return workflows.patch_receipt(receipt_id=receipt_id, body=body, user=user)


@router.delete("/api/receipts/{receipt_id}", status_code=204)
def delete_receipt(receipt_id: str, user: User = Depends(employee_only)) -> Response:
    """Only a draft that was never submitted can go; images and chat go with it."""
    return workflows.delete_receipt(receipt_id=receipt_id, user=user)


@router.post("/api/receipts/{receipt_id}/submit")
def submit(receipt_id: str, user: User = Depends(employee_only)) -> dict[str, Any]:
    return workflows.submit(receipt_id=receipt_id, user=user)
