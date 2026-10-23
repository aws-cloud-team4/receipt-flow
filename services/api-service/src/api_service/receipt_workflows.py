"""Receipt use cases: access checks, field updates, submission and review.

Routes delegate here; DynamoDB access stays in receiptflow_common.store.
"""

from typing import Any, Literal

from fastapi.responses import Response
from receiptflow_common import aws, store
from receiptflow_common.auth import User
from receiptflow_common.config import get_settings
from receiptflow_common.domain import (
    AI_FIELDS,
    CATEGORIES,
    EDITABLE_FIELDS,
    EDITABLE_STATUSES,
    EXPENSE_FIELDS,
    FIELD_LABELS,
    PROFILE_FIELDS,
    missing_required,
    normalize_fields,
    now_iso,
    review_points,
)
from receiptflow_common.errors import ApiError, forbidden, not_found

from api_service.schemas import ChangeRequest, PatchReceipt


def _load(receipt_id: str, user: User, *, owner_only: bool = False) -> dict[str, Any]:
    if user.is_admin:
        raise forbidden()
    receipt = store.get_receipt(receipt_id)
    if not receipt:
        raise not_found()
    is_owner = receipt["owner_sub"] == user.sub
    if not is_owner and (owner_only or not user.is_reviewer):
        raise forbidden()
    return receipt


def _require_editable(receipt: dict[str, Any]) -> None:
    if receipt["review_status"] not in EDITABLE_STATUSES:
        raise ApiError(409, "not_editable", "제출된 증빙은 수정할 수 없습니다.")


def _upload_target(receipt: dict[str, Any]) -> dict[str, Any]:
    """The browser uploads the original; preprocess-service crops it into incoming/."""
    s = get_settings()
    url = aws.client("s3").generate_presigned_url(
        "put_object",
        Params={"Bucket": s.bucket, "Key": f"raw/{receipt['id']}.jpg", "ContentType": "image/jpeg"},
        ExpiresIn=s.upload_url_ttl,
    )
    return {"url": url, "method": "PUT", "headers": {"Content-Type": "image/jpeg"}}


def create_receipt(*, user: User) -> dict[str, Any]:
    receipt = store.create_receipt(user.sub, user.name, "server", user.profile())
    return {"receipt": receipt, "upload": _upload_target(receipt)}


def reupload(receipt_id: str, *, user: User) -> dict[str, Any]:
    receipt = _load(receipt_id, user, owner_only=True)
    _require_editable(receipt)
    # It may be another receipt altogether: start over (the department comes from the profile and stays).
    cleared = {k: None for k in (*AI_FIELDS, *EXPENSE_FIELDS)}
    receipt = store.apply_fields(
        receipt,
        cleared,
        analysis_status="waiting",
        needs_check=[],
        analysis_error=None,
        preprocess=None,
        ai_filled=[],
        ai_context={},
        result_confirmed_at=None,
    )
    store.delete_messages(receipt_id)
    store.add_event(receipt_id, user.name, "reuploaded", "처음부터 다시 작성")
    return {"receipt": receipt, "upload": _upload_target(receipt)}


def uploaded(receipt_id: str, *, user: User) -> dict[str, Any]:
    """Called after preprocess-service wrote the cropped image."""
    _load(receipt_id, user, owner_only=True)
    try:
        # The worker may already have picked the image up; never move it backwards.
        return store.update_receipt(
            receipt_id,
            expect={"analysis_status": ("waiting", "failed")},
            analysis_status="queued",
            image_key=f"incoming/{receipt_id}.jpg",
            timings={"uploaded": now_iso()},
        )
    except store.ConflictError:
        return store.get_receipt(receipt_id)  # type: ignore[return-value]


def my_receipts(*, user: User) -> dict[str, Any]:
    items = [r for r in store.list_by_owner(user.sub) if r["analysis_status"] != "waiting"]
    return {"items": items}


def get_receipt(receipt_id: str, *, user: User) -> dict[str, Any]:
    receipt = _load(receipt_id, user)
    image_url = original_url = None
    if receipt.get("analysis_status") != "waiting":
        s = get_settings()

        def url(key: str) -> str:
            return aws.client("s3").generate_presigned_url(
                "get_object", Params={"Bucket": s.bucket, "Key": key}, ExpiresIn=s.image_url_ttl
            )

        image_url = url(f"incoming/{receipt_id}.jpg")  # cropped, what the AI read
        if receipt.get("preprocess"):
            original_url = url(f"raw/{receipt_id}.jpg")  # the photo as taken
    return {
        **receipt,
        "image_url": image_url,
        "original_url": original_url,
        "history": store.list_events(receipt_id),
        "review_points": review_points(receipt),
    }


def patch_receipt(receipt_id: str, body: PatchReceipt, *, user: User) -> dict[str, Any]:
    receipt = _load(receipt_id, user, owner_only=True)
    _require_editable(receipt)
    read_only = set(body.fields) & set(PROFILE_FIELDS)
    if read_only:
        raise ApiError(400, "read_only_field", "부서는 로그인 프로필 기준이라 바꿀 수 없습니다.")
    unknown = set(body.fields) - set(EDITABLE_FIELDS)
    if unknown:
        raise ApiError(400, "unknown_fields", f"알 수 없는 항목: {', '.join(sorted(unknown))}")
    fields = normalize_fields(body.fields)
    if body.fields.get("category") not in (None, "") and fields.get("category") is None:
        raise ApiError(
            400, "invalid_category", f"지출 분류는 {', '.join(CATEGORIES.values())} 중 하나입니다."
        )
    needs_check = [k for k in receipt.get("needs_check", []) if k not in fields]
    ai_filled = [k for k in receipt.get("ai_filled", []) if k not in fields]  # a person set these now
    try:
        return store.apply_fields(
            receipt,
            fields,
            expect={"review_status": EDITABLE_STATUSES},
            needs_check=needs_check,
            ai_filled=ai_filled,
        )
    except store.ConflictError as exc:
        raise ApiError(409, "not_editable", "제출된 증빙은 수정할 수 없습니다.") from exc


def delete_receipt(receipt_id: str, *, user: User) -> Response:
    """Only a draft that was never submitted can go; images and chat go with it."""
    receipt = _load(receipt_id, user, owner_only=True)
    try:
        store.delete_receipt(receipt["id"], expect_status=("draft",))
    except store.ConflictError as exc:
        raise ApiError(409, "not_deletable", "제출한 적 있는 증빙은 삭제할 수 없습니다.") from exc
    aws.client("s3").delete_objects(
        Bucket=get_settings().bucket,
        Delete={"Objects": [{"Key": f"{p}/{receipt_id}.jpg"} for p in ("raw", "incoming")], "Quiet": True},
    )
    return Response(status_code=204)


def submit(receipt_id: str, *, user: User) -> dict[str, Any]:
    receipt = _load(receipt_id, user, owner_only=True)
    _require_editable(receipt)
    if receipt["analysis_status"] in ("waiting", "queued", "processing"):
        raise ApiError(409, "analysis_pending", "AI 분석이 끝난 뒤 제출할 수 있습니다.")
    missing = missing_required(receipt.get("fields", {}))
    if missing:
        labels = ", ".join(FIELD_LABELS[k] for k in missing)
        raise ApiError(422, "missing_fields", f"필수 항목을 입력해 주세요: {labels}", fields=missing)
    if any(c["level"] == "error" for c in receipt.get("checks", [])):
        raise ApiError(422, "check_failed", "금액·날짜 오류를 먼저 확인해 주세요.")
    now = now_iso()
    try:
        receipt = store.update_receipt(
            receipt_id,
            expect={"review_status": EDITABLE_STATUSES},
            review_status="submitted",
            submitted_at=now,
            review_note=None,
            timings={"submitted": now},
        )
    except store.ConflictError as exc:
        raise ApiError(409, "not_editable", "이미 제출된 증빙입니다.") from exc
    store.add_event(receipt_id, user.name, "submitted", None)
    return receipt


def review_list(
    status: Literal["submitted", "approved", "changes_requested", "draft"] = "submitted", *, _: User
) -> dict[str, Any]:
    return {"items": [{**r, "review_points": review_points(r)} for r in store.list_by_status(status)]}


def _decide(
    receipt_id: str, user: User, status: str, action: str, note: str | None, fields: list[str] | None = None
) -> dict[str, Any]:
    if not store.get_receipt(receipt_id):
        raise not_found()
    try:
        receipt = store.update_receipt(
            receipt_id,
            expect={"review_status": ("submitted",)},
            review_status=status,
            review_note=note,
            review_fields=fields or [],
            reviewed_by=user.name,
            reviewed_at=now_iso(),
        )
    except store.ConflictError as exc:
        raise ApiError(409, "not_submitted", "제출 상태인 증빙만 처리할 수 있습니다.") from exc
    store.add_event(receipt_id, user.name, action, note)
    return receipt


def approve(receipt_id: str, *, user: User) -> dict[str, Any]:
    return _decide(receipt_id, user, "approved", "approved", None)


def request_changes(receipt_id: str, body: ChangeRequest, *, user: User) -> dict[str, Any]:
    allowed = {*EDITABLE_FIELDS, "photo"}
    unknown = sorted(set(body.fields) - allowed)
    if unknown:
        raise ApiError(400, "unknown_fields", f"알 수 없는 항목: {', '.join(unknown)}")
    return _decide(
        receipt_id,
        user,
        "changes_requested",
        "changes_requested",
        body.reason.strip(),
        list(dict.fromkeys(body.fields)),
    )
