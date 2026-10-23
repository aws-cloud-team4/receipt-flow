"""Admin API (/api/admin): accounts in the Cognito user pool and receipts in any status.

Admins only manage; they do not write or review receipts. A temporary password is returned once
in the response and never stored or logged.
"""

import secrets
import string
from typing import Any, Literal

from botocore.exceptions import ClientError
from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field
from receiptflow_common import aws, org, store
from receiptflow_common.auth import ROLE_LABELS, ROLES, Role, User, admin_only, role_from_groups
from receiptflow_common.config import get_settings
from receiptflow_common.domain import REVIEW_STATUSES
from receiptflow_common.errors import ApiError, not_found

router = APIRouter(prefix="/api/admin", dependencies=[Depends(admin_only)])

PROFILE = ("employee_no", "department", "position")


class NewUser(BaseModel):
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$", max_length=120)
    name: str = Field(min_length=1, max_length=50)
    department: str | None = Field(default=None, max_length=50)  # not for admins
    position: str = Field(max_length=50)
    role: Literal["employee", "reviewer", "admin"] = "employee"


class UserPatch(BaseModel):  # the employee number never changes
    name: str | None = Field(default=None, min_length=1, max_length=50)
    department: str | None = Field(default=None, max_length=50)
    position: str | None = Field(default=None, max_length=50)
    role: Literal["employee", "reviewer", "admin"] | None = None


def _check_reviewer(role: str | None, department: str | None) -> None:
    if role == "reviewer" and department != org.REVIEWER_DEPARTMENT:
        raise ApiError(
            400, "reviewer_department", f"검수 담당자는 {org.REVIEWER_DEPARTMENT} 소속이어야 해요."
        )


def _check_org(department: str | None, position: str | None, keep: dict[str, Any] | None = None) -> None:
    """Values must come from the lists; on an edit, the account's current (older) value may stay."""
    keep = keep or {}
    if department and department not in org.DEPARTMENT_CODES and department != keep.get("department"):
        raise ApiError(400, "invalid_department", "목록에 있는 부서를 골라 주세요.")
    if position and position not in org.POSITIONS and position != keep.get("position"):
        raise ApiError(400, "invalid_position", "목록에 있는 직급을 골라 주세요.")


def _idp():
    return aws.client("cognito-idp")


def _pool() -> str:
    return get_settings().cognito_pool_id


def temporary_password() -> str:
    """Meets the pool policy (10+ chars, lower case, digits)."""
    alphabet = string.ascii_letters + string.digits
    while True:
        pw = "".join(secrets.choice(alphabet) for _ in range(14))
        if any(c.islower() for c in pw) and any(c.isupper() for c in pw) and any(c.isdigit() for c in pw):
            return pw


def _attrs(raw: list[dict[str, str]]) -> dict[str, str]:
    return {a["Name"]: a["Value"] for a in raw}


def _groups(username: str) -> list[str]:
    resp = _idp().admin_list_groups_for_user(UserPoolId=_pool(), Username=username)
    return [g["GroupName"] for g in resp.get("Groups", [])]


def _view(
    username: str, attrs: dict[str, str], status: str, enabled: bool, created: Any, role: Role
) -> dict[str, Any]:
    return {
        "username": username,
        "sub": attrs.get("sub"),
        "email": attrs.get("email"),
        "name": attrs.get("name"),
        **{k: attrs.get(f"custom:{k}") for k in PROFILE},
        "role": role,
        "role_label": ROLE_LABELS[role],
        "status": status,
        "enabled": enabled,
        "created_at": created.isoformat() if hasattr(created, "isoformat") else created,
    }


def _get(username: str) -> dict[str, Any]:
    try:
        u = _idp().admin_get_user(UserPoolId=_pool(), Username=username)
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "UserNotFoundException":
            raise not_found("계정") from exc
        raise
    return _view(
        u["Username"],
        _attrs(u.get("UserAttributes", [])),
        u["UserStatus"],
        u["Enabled"],
        u.get("UserCreateDate"),
        role_from_groups(_groups(u["Username"])),
    )


def _set_role(username: str, role: Role) -> None:
    for g in _groups(username):
        if g in ROLES and g != role:
            _idp().admin_remove_user_from_group(UserPoolId=_pool(), Username=username, GroupName=g)
    _idp().admin_add_user_to_group(UserPoolId=_pool(), Username=username, GroupName=role)


def _is_self(target: dict[str, Any], me: User) -> bool:
    return target.get("sub") == me.sub or (target.get("email") or "").lower() == me.email.lower()


@router.get("/options")
def options() -> dict[str, Any]:
    return org.options()


def _all_users() -> list[dict[str, Any]]:
    members: dict[str, list[str]] = {}
    for role in ROLES:
        kwargs: dict[str, Any] = {"UserPoolId": _pool(), "GroupName": role}
        while True:
            try:
                resp = _idp().list_users_in_group(**kwargs)
            except ClientError as exc:
                if exc.response["Error"]["Code"] != "ResourceNotFoundException":
                    raise
                break  # a role group not created yet (e.g. admin before the infra apply)
            for u in resp.get("Users", []):
                members.setdefault(u["Username"], []).append(role)
            if not resp.get("NextToken"):
                break
            kwargs["NextToken"] = resp["NextToken"]
    items: list[dict[str, Any]] = []
    kwargs = {"UserPoolId": _pool()}
    while True:
        resp = _idp().list_users(**kwargs)
        for u in resp.get("Users", []):
            items.append(
                _view(
                    u["Username"],
                    _attrs(u.get("Attributes", [])),
                    u["UserStatus"],
                    u["Enabled"],
                    u.get("UserCreateDate"),
                    role_from_groups(members.get(u["Username"], [])),
                )
            )
        if not resp.get("PaginationToken"):
            break
        kwargs["PaginationToken"] = resp["PaginationToken"]
    return items


@router.get("/users")
def list_users() -> dict[str, Any]:
    items = _all_users()
    items.sort(key=lambda x: (x["role"] != "admin", x["role"] != "reviewer", x.get("name") or ""))
    return {"items": items}


def _new_employee_no(department: str | None) -> str:
    """Department code + current year + next 3-digit sequence for that pair (DEV2026001)."""
    prefix = org.employee_no_prefix(department)
    floor = org.highest_sequence(prefix, [u.get("employee_no") for u in _all_users()])
    n = store.next_sequence(f"EMPNO#{prefix}", floor)
    if n > 999:
        raise ApiError(409, "employee_no_full", "이 부서·입사 연도의 사번이 모두 찼어요.")
    return f"{prefix}{n:03d}"


@router.post("/users", status_code=201)
def create_user(body: NewUser) -> dict[str, Any]:
    email = body.email.lower()
    department = None if body.role == "admin" else body.department  # admins only manage: no department
    if body.role != "admin" and department not in org.DEPARTMENT_CODES:
        raise ApiError(400, "invalid_department", "목록에 있는 부서를 골라 주세요.")
    _check_org(department, body.position)
    _check_reviewer(body.role, department)
    try:
        _idp().admin_get_user(UserPoolId=_pool(), Username=email)
        raise ApiError(409, "user_exists", "같은 이메일의 계정이 이미 있어요.")
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "UserNotFoundException":
            raise
    pw = temporary_password()
    attrs = [
        {"Name": "email", "Value": email},
        {"Name": "email_verified", "Value": "true"},
        {"Name": "name", "Value": body.name.strip()},
        {"Name": "custom:employee_no", "Value": _new_employee_no(department)},
        {"Name": "custom:position", "Value": body.position},
    ] + ([{"Name": "custom:department", "Value": department}] if department else [])
    try:
        _idp().admin_create_user(
            UserPoolId=_pool(),
            Username=email,
            TemporaryPassword=pw,  # first sign-in asks for a new one
            MessageAction="SUPPRESS",  # no email; the admin hands it over
            UserAttributes=attrs,
        )
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "UsernameExistsException":
            raise ApiError(409, "user_exists", "같은 이메일의 계정이 이미 있어요.") from exc
        raise
    _set_role(email, body.role)
    return {"user": _get(email), "temporary_password": pw}


@router.patch("/users/{username}")
def update_user(username: str, body: UserPatch, me: User = Depends(admin_only)) -> dict[str, Any]:
    target = _get(username)
    if body.role and body.role != "admin" and target["role"] == "admin" and _is_self(target, me):
        raise ApiError(409, "self_demote", "자기 자신의 관리자 권한은 뺄 수 없어요.")
    _check_org(body.department, body.position, keep=target)
    _check_reviewer(body.role or target["role"], body.department or target.get("department"))
    editable = ("department", "position")
    changes = {"name": body.name, **{k: getattr(body, k) for k in editable}}
    set_attrs = [
        {"Name": ("name" if k == "name" else f"custom:{k}"), "Value": v.strip()}
        for k, v in changes.items()
        if v is not None and v.strip()
    ]
    clear = [f"custom:{k}" for k in editable if getattr(body, k) is not None and not getattr(body, k).strip()]
    if set_attrs:
        _idp().admin_update_user_attributes(UserPoolId=_pool(), Username=username, UserAttributes=set_attrs)
    if clear:
        _idp().admin_delete_user_attributes(UserPoolId=_pool(), Username=username, UserAttributeNames=clear)
    if body.role and body.role != target["role"]:
        _set_role(username, body.role)
    return {"user": _get(username)}


@router.post("/users/{username}/temporary-password")
def reset_password(username: str) -> dict[str, Any]:
    _get(username)
    pw = temporary_password()
    _idp().admin_set_user_password(UserPoolId=_pool(), Username=username, Password=pw, Permanent=False)
    return {"temporary_password": pw}


@router.post("/users/{username}/disable")
def disable_user(username: str, me: User = Depends(admin_only)) -> dict[str, Any]:
    if _is_self(_get(username), me):
        raise ApiError(409, "self_disable", "자기 자신은 사용 중지할 수 없어요.")
    _idp().admin_disable_user(UserPoolId=_pool(), Username=username)
    return {"user": _get(username)}


@router.delete("/users/{username}", status_code=204)
def delete_user(username: str, me: User = Depends(admin_only)) -> Response:
    """For good; receipts the person made stay (they keep the submitter's name)."""
    if _is_self(_get(username), me):
        raise ApiError(409, "self_delete", "자기 자신은 삭제할 수 없어요.")
    _idp().admin_delete_user(UserPoolId=_pool(), Username=username)
    return Response(status_code=204)


@router.post("/users/{username}/enable")
def enable_user(username: str) -> dict[str, Any]:
    _get(username)
    _idp().admin_enable_user(UserPoolId=_pool(), Username=username)
    return {"user": _get(username)}


@router.get("/receipts")
def list_receipts(status: str = Query(pattern="^(" + "|".join(REVIEW_STATUSES) + ")$")) -> dict[str, Any]:
    return {"items": store.list_by_status(status)}


@router.delete("/receipts/{receipt_id}", status_code=204)
def delete_receipt(receipt_id: str, me: User = Depends(admin_only)) -> Response:
    receipt = store.get_receipt(receipt_id)
    if not receipt:
        raise not_found()
    try:
        store.delete_receipt(receipt_id, expect_status=None)
    except store.ConflictError as exc:  # already gone
        raise not_found() from exc
    aws.client("s3").delete_objects(
        Bucket=get_settings().bucket,
        Delete={"Objects": [{"Key": f"{p}/{receipt_id}.jpg"} for p in ("raw", "incoming")], "Quiet": True},
    )
    store.log_deletion(receipt, me.name)
    return Response(status_code=204)


@router.get("/deletions")
def deletions() -> dict[str, Any]:
    return {"items": store.list_deletions()}


@router.delete("/deletions/{key:path}", status_code=204)
def delete_deletion(key: str) -> Response:
    if not store.delete_deletion(key):
        raise not_found("삭제 기록")
    return Response(status_code=204)


@router.delete("/deletions", status_code=204)
def clear_deletions() -> Response:
    store.delete_deletion(None)
    return Response(status_code=204)
