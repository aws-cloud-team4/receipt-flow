"""Write services/.env and web/.env.local from the shared AWS resources, using your own AWS login.

Read-only: it only looks the resources up (STS, DynamoDB, S3, SQS, Cognito describe/list/get) and
changes nothing in AWS. Use it instead of `terraform output` when you don't have the Terraform state.

    cd services
    uv run python scripts/make_env.py                  # profile team-admin, refuses to overwrite
    uv run python scripts/make_env.py --force          # overwrite (old files kept as *.bak)
    uv run python scripts/make_env.py --print          # only show what it would write
    uv run python scripts/make_env.py --dev-login      # also turn on the local developer login

Uses boto3 directly (not receiptflow_common.aws): that one needs the .env this script writes.
"""

import argparse
import shutil
import sys
from pathlib import Path

import boto3
from botocore.exceptions import BotoCoreError, ClientError

ROOT = Path(__file__).resolve().parents[2]
SERVICES_ENV = ROOT / "services" / ".env"
WEB_ENV = ROOT / "web" / ".env.local"
NAME = "receipt-flow-dev"  # infra/terraform/base: "${var.project}-${var.env}"
EXTRACT_MODEL = "global.anthropic.claude-sonnet-5-5"
CHAT_MODEL = "global.anthropic.claude-haiku-5-5"


def find(session: boto3.Session, region: str) -> dict[str, str]:
    """Look up the shared resources by their Terraform names; exit with a hint if one is missing."""
    identity = session.client("sts").get_caller_identity()
    if identity["Arn"].endswith(":root"):
        sys.exit("루트 계정으로 로그인되어 있어요. 본인 IAM 사용자로 로그인해 주세요.")
    account = identity["Account"]
    print(f"AWS 계정 {account} · {identity['Arn'].split('/')[-1]}")

    def need(what: str, value: str | None) -> str:
        if not value:
            sys.exit(
                f"{what}을(를) 찾지 못했어요. "
                "infra/terraform/base가 이 계정·리전에 만들어져 있는지 확인해 주세요."
            )
        print(f"  [ok] {what}: {value}")
        return value

    session.client("dynamodb", region_name=region).describe_table(TableName=NAME)
    table = need("DynamoDB 테이블", NAME)
    bucket = f"{NAME}-receipts-{account}"
    session.client("s3", region_name=region).head_bucket(Bucket=bucket)
    need("S3 버킷", bucket)
    queue = need(
        "SQS 큐",
        session.client("sqs", region_name=region).get_queue_url(QueueName=f"{NAME}-analysis")["QueueUrl"],
    )

    cognito = session.client("cognito-idp", region_name=region)
    pools = [
        p
        for page in cognito.get_paginator("list_user_pools").paginate(MaxResults=60)
        for p in page["UserPools"]
    ]
    pool = need("Cognito 사용자 풀", next((p["Id"] for p in pools if p["Name"] == NAME), None))
    clients = cognito.list_user_pool_clients(UserPoolId=pool, MaxResults=60)["UserPoolClients"]
    client = need(
        "Cognito 웹 클라이언트",
        next((c["ClientId"] for c in clients if c["ClientName"] == f"{NAME}-web"), None),
    )
    return {"table": table, "bucket": bucket, "queue": queue, "pool": pool, "client": client}


def render(found: dict[str, str], region: str, profile: str, dev_login: bool) -> tuple[str, str]:
    services = f"""RF_REGION={region}
RF_TABLE={found["table"]}
RF_BUCKET={found["bucket"]}
RF_QUEUE_URL={found["queue"]}
RF_AUTH_MODE=cognito
RF_COGNITO_POOL_ID={found["pool"]}
RF_COGNITO_CLIENT_ID={found["client"]}
RF_AI_MODE=bedrock
RF_EXTRACT_MODEL={EXTRACT_MODEL}
RF_CHAT_MODEL={CHAT_MODEL}
RF_CORS_ORIGINS=http://localhost:5173
AWS_PROFILE={profile}

# local only: hidden developer login with the test accounts (never set in deploy)
RF_DEV_LOGIN={"true" if dev_login else "false"}
"""
    web = f"""VITE_REGION={region}
VITE_COGNITO_CLIENT_ID={found["client"]}
VITE_AUTH_MODE=cognito
"""
    return services, web


def write(path: Path, text: str, force: bool) -> None:
    if path.exists():
        if not force:
            print(f"  · {path.relative_to(ROOT)} 이미 있어서 그대로 둬요 (바꾸려면 --force)")
            return
        shutil.copyfile(path, path.with_name(path.name + ".bak"))
    path.write_text(text, encoding="utf-8", newline="\n")
    print(f"  [ok] {path.relative_to(ROOT)} 저장")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--profile", default="team-admin", help="AWS CLI 프로필 (기본 team-admin)")
    p.add_argument("--region", default="ap-northeast-2")
    p.add_argument("--force", action="store_true", help="있는 파일을 덮어쓰기 (*.bak로 보관)")
    p.add_argument("--print", dest="show", action="store_true", help="파일을 쓰지 않고 내용만 보여 주기")
    p.add_argument("--dev-login", action="store_true", help="로컬 개발자 로그인(테스트 계정) 켜기")
    args = p.parse_args()

    try:
        found = find(boto3.Session(profile_name=args.profile), args.region)
    except (BotoCoreError, ClientError) as e:
        sys.exit(
            f"AWS 조회 실패: {e}\n먼저 `aws login --profile {args.profile}`로 로그인했는지 확인해 주세요."
        )

    services, web = render(found, args.region, args.profile, args.dev_login)
    if args.show:
        print(f"\n# services/.env\n{services}\n# web/.env.local\n{web}")
        return
    write(SERVICES_ENV, services, args.force)
    write(WEB_ENV, web, args.force)


if __name__ == "__main__":
    main()
