"""Create the first real accounts in Cognito (idempotent): the admin who then makes everyone else.

uv run python scripts/seed_users.py

New users get a temporary password (saved to scripts/demo-users.local.json, gitignored) and must set
their own on first sign-in. Existing users keep their password; only profile and group are synced.
To hand someone a new temporary password: scripts/issue_temp_password.py.
"""

import json
import secrets
import string
from pathlib import Path

from receiptflow_common import aws
from receiptflow_common.config import get_settings

USERS = [  # real accounts made by script; everyone else is created on the admin screen
    {
        "email": "admin1@dev.com",
        "name": "관리자",
        "group": "admin",
        "department": "경영지원부",
        "position": "부장",
        "employee_no": "MGT2026001",
    },
]
PROFILE = ("department", "position", "employee_no")
OUT = Path(__file__).with_name("demo-users.local.json")


def password() -> str:
    alphabet = string.ascii_letters + string.digits
    while True:
        pw = "".join(secrets.choice(alphabet) for _ in range(14))
        if any(c.islower() for c in pw) and any(c.isdigit() for c in pw):
            return pw


def main() -> None:
    s = get_settings()
    idp = aws.client("cognito-idp")
    saved = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    for u in USERS:
        created = False
        try:
            pw = password()
            idp.admin_create_user(
                UserPoolId=s.cognito_pool_id,
                Username=u["email"],
                TemporaryPassword=pw,  # first sign-in asks for a new one (NEW_PASSWORD_REQUIRED)
                MessageAction="SUPPRESS",
                UserAttributes=[
                    {"Name": "email", "Value": u["email"]},
                    {"Name": "email_verified", "Value": "true"},
                    {"Name": "name", "Value": u["name"]},
                ],
            )
            created = True
            saved[u["email"]] = pw
            print("created", u["email"], "(temporary password)")
        except idp.exceptions.UsernameExistsException:
            print("exists ", u["email"], "(password unchanged)")
        idp.admin_update_user_attributes(
            UserPoolId=s.cognito_pool_id,
            Username=u["email"],
            UserAttributes=[{"Name": "name", "Value": u["name"]}]
            + [{"Name": f"custom:{k}", "Value": u[k]} for k in PROFILE],
        )
        idp.admin_add_user_to_group(UserPoolId=s.cognito_pool_id, Username=u["email"], GroupName=u["group"])
        if created:
            OUT.write_text(json.dumps(saved, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"temporary passwords of new users: {OUT}")


if __name__ == "__main__":
    main()
