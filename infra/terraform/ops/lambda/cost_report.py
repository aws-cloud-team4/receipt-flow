"""Weekly cost email (EventBridge, Mondays 09:00 KST) to the SNS topic's email subscribers.

The account's organization blocks the Cost Explorer API (SCP), so the number comes from AWS Budgets:
the project total since the team started (budget "aws-team4-receipt-flow", a custom period starting
2026-10-01, refreshed by AWS a few times a day). Only that figure is mailed; the change since last
week's report is kept in an SSM parameter.
It also lists anything billed by the hour that is running right now (EKS, EC2, load balancers, NAT
gateways, idle Elastic IPs), the usual cause of surprises.
"""

import os
from datetime import date

import boto3

budgets = boto3.client("budgets", region_name="us-east-1")  # Budgets is a global service
ssm = boto3.client("ssm")
sns = boto3.client("sns")
ec2 = boto3.client("ec2")
eks = boto3.client("eks")
elb = boto3.client("elbv2")

ACCOUNT = os.environ["ACCOUNT_ID"]
BUDGET = float(os.environ.get("BUDGET_USD", "200"))
END = date.fromisoformat(os.environ.get("BUDGET_END", "2026-11-14"))
START = date.fromisoformat(os.environ.get("START", "2026-10-01"))
LAST = os.environ["LAST_PARAM"]


def usd(x: float) -> str:
    return f"${x:,.2f}"


def spend(name: str) -> tuple[float, float]:
    calc = budgets.describe_budget(AccountId=ACCOUNT, BudgetName=name)["Budget"].get("CalculatedSpend", {})
    return (float(calc.get("ActualSpend", {}).get("Amount", 0)), float(calc.get("ForecastedSpend", {}).get("Amount", 0)))


def running() -> list[str]:
    out = [f"EKS 클러스터 {n}" for n in eks.list_clusters()["clusters"]]
    for r in ec2.describe_instances(Filters=[{"Name": "instance-state-name", "Values": ["pending", "running"]}])["Reservations"]:
        out += [f"EC2 {i['InstanceType']} ({i['InstanceId']})" for i in r["Instances"]]
    out += [f"로드밸런서 {lb['LoadBalancerName']}" for lb in elb.describe_load_balancers()["LoadBalancers"]]
    out += [
        f"NAT 게이트웨이 {n['NatGatewayId']}"
        for n in ec2.describe_nat_gateways(Filter=[{"Name": "state", "Values": ["available", "pending"]}])["NatGateways"]
    ]
    out += [f"연결 안 된 Elastic IP {a['PublicIp']}" for a in ec2.describe_addresses()["Addresses"] if "AssociationId" not in a]
    return out


def handler(event=None, context=None):
    today = date.today()
    total, _ = spend(os.environ["PROJECT_BUDGET"])  # since START
    try:
        last = float(ssm.get_parameter(Name=LAST)["Parameter"]["Value"])
    except (ssm.exceptions.ParameterNotFound, ValueError):
        last = None
    live = running()

    since = f"{START.month}월 {START.day}일" if START.day != 1 else f"{START.month}월"
    lines = [
        f"receiptflow AWS 비용 주간 보고 ({today.isoformat()})",
        "",
        f"{since}부터 누적: {usd(total)} / 예산 {usd(BUDGET)}  (남은 금액 {usd(BUDGET - total)})",
        "  " + (f"지난 보고 이후 +{usd(total - last)}" if last is not None else "다음 보고부터 지난주 대비 증가분을 표시합니다"),
        f"{END.isoformat()}까지 {max((END - today).days, 0)}일",
        "",
        "지금 켜져 있는 시간당 과금 리소스:",
        *([f"  - {x}" for x in live] or ["  - 없음"]),
        "",
        "숫자는 AWS Budgets 기준(하루 몇 번 갱신)입니다. 서비스별 내역은 조직 정책으로 Cost Explorer가 막혀 있어 볼 수 없습니다.",
        "켜진 리소스가 있으면 deploy/README.md의 정리 절차를 확인하세요.",
    ]
    sns.publish(
        TopicArn=os.environ["TOPIC_ARN"],
        Subject=f"[receiptflow] AWS 비용 주간 보고 {today.isoformat()} - {since}부터 {usd(total)}" + (" · 켜진 리소스 있음" if live else ""),
        Message="\n".join(lines),
    )
    ssm.put_parameter(Name=LAST, Value=f"{total:.2f}", Type="String", Overwrite=True)
    return {"since_start": total, "running": live}
