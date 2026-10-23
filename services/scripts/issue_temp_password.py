"""Set a user's password. Admin only.

    uv run python scripts/issue_temp_password.py employee1@example.com          # temporary password
    uv run python scripts/issue_temp_password.py employee1@example.com --set    # choose it now

Default: prints a random temporary password (valid 7 days). The user signs in with it once and
must then set their own password (first-login change, NEW_PASSWORD_REQUIRED).
--set: asks for a password at a hidden prompt and makes it permanent, skipping the first-login
change. Meant for demo accounts during development.
"""

import argparse
import getpass
import secrets
import string

from receiptflow_common import aws
from receiptflow_common.config import get_settings


def temp_password() -> str:
    alphabet = string.ascii_letters + string.digits
    while True:
        pw = "".join(secrets.choice(alphabet) for _ in range(12))
        if any(c.islower() for c in pw) and any(c.isdigit() for c in pw):
            return pw


def ask_password() -> str:
    while True:
        pw = getpass.getpass("new password (10+ chars, a lowercase letter and a digit): ")
        if len(pw) < 10 or not any(c.islower() for c in pw) or not any(c.isdigit() for c in pw):
            print("does not meet the policy, try again")
            continue
        if getpass.getpass("again: ") != pw:
            print("the two entries differ, try again")
            continue
        return pw


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("email")
    ap.add_argument("--set", action="store_true", help="choose a permanent password now")
    args = ap.parse_args()

    s = get_settings()
    idp = aws.client("cognito-idp")
    user = idp.admin_get_user(UserPoolId=s.cognito_pool_id, Username=args.email)
    name = next((a["Value"] for a in user["UserAttributes"] if a["Name"] == "name"), args.email)

    if args.set:
        pw = ask_password()
        idp.admin_set_user_password(
            UserPoolId=s.cognito_pool_id, Username=args.email, Password=pw, Permanent=True
        )
        print(f"password set for {name} ({args.email}); sign in with it directly")
        return

    pw = temp_password()
    idp.admin_set_user_password(
        UserPoolId=s.cognito_pool_id, Username=args.email, Password=pw, Permanent=False
    )
    print(f"{name} ({args.email}) temporary password: {pw}")
    print("Give it to the user directly; they will set a new password at first sign-in.")


if __name__ == "__main__":
    main()
