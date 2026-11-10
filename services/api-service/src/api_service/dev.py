"""Developer login support: the test accounts (RF_DEV_LOGIN locally; RF_DEMO_LOGIN in deploy, no admin)."""

from typing import Any

from fastapi import APIRouter
from receiptflow_common.auth import dev_profiles
from receiptflow_common.config import get_settings
from receiptflow_common.errors import not_found

router = APIRouter(prefix="/api/dev")


@router.get("/profiles")
def profiles() -> dict[str, Any]:
    s = get_settings()
    if s.dev_login or s.auth_mode == "dev":
        return {"items": dev_profiles()}
    if s.demo_login:
        return {"items": dev_profiles(include_admin=False)}
    raise not_found("개발자 로그인")
