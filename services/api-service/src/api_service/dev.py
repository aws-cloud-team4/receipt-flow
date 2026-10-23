"""Developer login support (local only): the test accounts, when RF_DEV_LOGIN is on."""

from typing import Any

from fastapi import APIRouter
from receiptflow_common.auth import dev_profiles
from receiptflow_common.config import get_settings
from receiptflow_common.errors import not_found

router = APIRouter(prefix="/api/dev")


@router.get("/profiles")
def profiles() -> dict[str, Any]:
    s = get_settings()
    if not (s.dev_login or s.auth_mode == "dev"):
        raise not_found("개발자 로그인")
    return {"items": dev_profiles()}
