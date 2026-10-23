"""Cognito ID-token verification shared by every HTTP service.

RF_AUTH_MODE=dev accepts only `Bearer dev:<sub>:<role>[:<id>]` so tests and offline work need no Cognito.
RF_DEV_LOGIN=true (local services/.env only) accepts those dev tokens next to Cognito ones: the hidden
developer login with the test accounts below.
Profile (name, department, position, employee number) comes from Cognito attributes in the ID token:
`name`, `custom:department`, `custom:position`, `custom:employee_no`; role comes from the group.
"""

from dataclasses import dataclass
from functools import lru_cache
from typing import Literal

import jwt
from fastapi import Depends, Header

from .config import Settings, get_settings
from .errors import ApiError

Role = Literal["employee", "reviewer", "admin"]
ROLES: tuple[Role, ...] = ("employee", "reviewer", "admin")


ROLE_LABELS = {"employee": "직원", "reviewer": "검수 담당자", "admin": "관리자"}

# Test accounts for dev tokens (header values must be ASCII, so the token carries only an id).
# id: (name, department, position, employee number, role). Fictional people; data by scripts/seed_dev_data.py.
DEV_PROFILES: dict[
    str, tuple[str, str | None, str, str, Role]
] = {  # numbers in the 9xx range: never a real one
    "kim": ("김민준", "영업부", "대리", "SAL2026901", "employee"),
    "lee": ("이서연", "개발부", "사원", "DEV2026901", "employee"),
    "choi": ("최지우", "마케팅부", "과장", "MKT2026901", "employee"),
    "jung": ("정도윤", "개발부", "주임", "DEV2026902", "employee"),
    "kang": ("강하은", "영업부", "사원", "SAL2026902", "employee"),
    "yoon": ("윤지호", "기획부", "차장", "PLN2026901", "employee"),
    "han": ("한예린", "감사부", "대리", "AUD2026901", "employee"),
    "park": ("박서준", "재무회계부", "과장", "ACC2026901", "reviewer"),
    "seo": ("서유나", "재무회계부", "부장", "ACC2026902", "reviewer"),
    "admin": ("오태민", None, "부장", "ADM2026901", "admin"),  # admins have no department
}


@dataclass(frozen=True)
class User:
    sub: str
    email: str
    name: str
    role: Role
    department: str | None = None
    position: str | None = None
    employee_no: str | None = None

    def profile(self) -> dict[str, str | None]:
        return {
            "sub": self.sub,
            "email": self.email,
            "name": self.name,
            "employee_no": self.employee_no,
            "department": self.department,
            "position": self.position,
            "role": self.role,
            "role_label": ROLE_LABELS[self.role],
        }

    @property
    def is_reviewer(self) -> bool:
        return self.role == "reviewer"

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


def _unauthorized(message: str = "로그인이 필요합니다.") -> ApiError:
    return ApiError(401, "unauthorized", message)


@lru_cache
def _jwks(pool_id: str, region: str) -> jwt.PyJWKClient:
    return jwt.PyJWKClient(f"https://cognito-idp.{region}.amazonaws.com/{pool_id}/.well-known/jwks.json")


def _verify_cognito(token: str, s: Settings) -> User:
    issuer = f"https://cognito-idp.{s.region}.amazonaws.com/{s.cognito_pool_id}"
    try:
        key = _jwks(s.cognito_pool_id, s.region).get_signing_key_from_jwt(token)
        claims = jwt.decode(token, key.key, algorithms=["RS256"], audience=s.cognito_client_id, issuer=issuer)
    except jwt.PyJWTError as exc:
        raise _unauthorized("세션이 만료되었거나 올바르지 않습니다.") from exc
    if claims.get("token_use") != "id":
        raise _unauthorized("ID 토큰이 필요합니다.")
    groups = claims.get("cognito:groups") or []
    email = claims.get("email", "")
    return User(
        sub=claims["sub"],
        email=email,
        name=claims.get("name") or email.split("@")[0],
        role=role_from_groups(groups),
        department=claims.get("custom:department"),
        position=claims.get("custom:position"),
        employee_no=claims.get("custom:employee_no"),
    )


def role_from_groups(groups: list[str]) -> Role:
    """One role per person; with several groups the strongest wins."""
    return "admin" if "admin" in groups else "reviewer" if "reviewer" in groups else "employee"


def _verify_dev(token: str) -> User:
    parts = token.split(":")
    if len(parts) < 3 or parts[0] != "dev" or parts[2] not in ROLES:
        raise _unauthorized()
    dev_id = parts[3] if len(parts) > 3 else parts[1]
    name, department, position, employee_no, _ = DEV_PROFILES.get(
        dev_id, (dev_id, None, None, None, "employee")
    )
    return User(
        sub=parts[1],
        email=f"{dev_id}@dev.local",
        name=name,
        role=parts[2],  # type: ignore[arg-type]
        department=department,
        position=position,
        employee_no=employee_no,
    )


def authenticate(token: str, s: Settings | None = None) -> User:
    s = s or get_settings()
    if s.auth_mode == "dev" or (s.dev_login and token.startswith("dev:")):
        return _verify_dev(token)
    return _verify_cognito(token, s)


def dev_profiles() -> list[dict[str, str]]:
    return [
        {
            "id": i,
            "name": n,
            "role": r,
            "role_label": ROLE_LABELS[r],
            "department": d,
            "position": p,
            "employee_no": e,
        }
        for i, (n, d, p, e, r) in DEV_PROFILES.items()
    ]


def current_user(authorization: str = Header(default="")) -> User:
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise _unauthorized()
    return authenticate(token)


def employee_only(user: User = Depends(current_user)) -> User:
    if user.role != "employee":
        raise ApiError(403, "forbidden", "직원만 사용할 수 있습니다.")
    return user


def reviewer_only(user: User = Depends(current_user)) -> User:
    if not user.is_reviewer:
        raise ApiError(403, "forbidden", "담당자만 사용할 수 있습니다.")
    return user


def admin_only(user: User = Depends(current_user)) -> User:
    if not user.is_admin:
        raise ApiError(403, "forbidden", "관리자만 사용할 수 있습니다.")
    return user
