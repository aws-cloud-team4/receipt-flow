"""Company structure for accounts: departments (with a 3-letter code), positions, and the
employee number rule (department code + year of creation + 3-digit sequence, e.g. DEV2026001)."""

import re
from datetime import datetime, timedelta, timezone

DEPARTMENTS: list[tuple[str, str, str]] = [  # (code, department, what it does)
    ("MGT", "경영지원부", "인사, 총무, 법무"),
    ("ACC", "재무회계부", "회계, 결산, 증빙 검토"),
    ("PLN", "기획부", "사업·전략 기획"),
    ("SAL", "영업부", "국내외 영업"),
    ("MKT", "마케팅부", "광고, 홍보, 브랜드"),
    ("DEV", "개발부", "서비스 개발, 인프라, 데이터"),
    ("AUD", "감사부", "내부 감사, 준법 점검"),
]
REVIEWER_DEPARTMENT = "재무회계부"  # reviewing receipts is the accounting department's job
POSITIONS = [
    "사원",
    "주임",
    "대리",
    "과장",
    "차장",
    "부장",
]  # 직급 (rank), lowest first; 팀장 is a role, not a rank

DEPARTMENT_CODES = {name: code for code, name, _ in DEPARTMENTS}
KST = timezone(timedelta(hours=9))  # fixed offset: no tz database needed (Windows), no DST in Korea


def this_year() -> int:
    return datetime.now(KST).year


def options() -> dict:
    return {
        "departments": [{"code": c, "name": n, "description": d} for c, n, d in DEPARTMENTS],
        "positions": POSITIONS,
        "reviewer_department": REVIEWER_DEPARTMENT,
    }


ADMIN_CODE = "ADM"  # admins have no department; their numbers start with this


def employee_no_prefix(department: str | None) -> str:
    """Department code (ADM for an admin without one) + the current year: DEV2026."""
    return f"{DEPARTMENT_CODES[department] if department else ADMIN_CODE}{this_year()}"


def highest_sequence(prefix: str, existing: list[str | None]) -> int:
    """Largest 3-digit sequence among employee numbers that start with `prefix` (0 if none)."""
    pattern = re.compile(rf"^{re.escape(prefix)}(\d{{3}})$")
    return max((int(m.group(1)) for no in existing if no and (m := pattern.match(no))), default=0)
