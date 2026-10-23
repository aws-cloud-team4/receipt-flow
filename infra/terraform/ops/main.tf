# Cost watch for the team account: budget alarms and a weekly cost email (Mondays 09:00 KST).
# Email addresses are personal data, so they are not in git: pass them at plan/apply time, e.g. in a
# local (git-ignored) infra/terraform/ops/terraform.tfvars:
#   report_emails = ["someone@example.com"]
# They are required on purpose: an apply without them stops instead of quietly removing the emails.
# Each address gets an SNS "confirm subscription" mail once; the weekly report starts after confirming.
# The organization's SCP blocks the Cost Explorer API, so the report reads AWS Budgets (this month, this year)
# and lists hourly-billed resources that are running. Cost: within the free tiers.

terraform {
  required_version = ">= 1.11"
  backend "s3" {
    bucket       = "receipt-flow-tfstate-431777499129"
    key          = "ops/terraform.tfstate"
    region       = "ap-northeast-2"
    profile      = "team-admin"
    encrypt      = true
    use_lockfile = true
  }
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.0"
    }
  }
}

variable "region" {
  type    = string
  default = "ap-northeast-2"
}

variable "aws_profile" {
  type    = string
  default = "team-admin"
}

variable "report_emails" {
  description = "Who gets the weekly cost email and the budget alarms (kept out of git: local terraform.tfvars)."
  type        = list(string)
  validation {
    condition     = length(var.report_emails) > 0
    error_message = "Give at least one email (report_emails in a local terraform.tfvars)."
  }
}

variable "budget_usd" {
  description = "Total budget for the project period."
  type        = number
  default     = 200
}

variable "project_start" {
  description = "First day the team's spending counts (the project total starts here)."
  type        = string
  default     = "2026-10-01"
}

variable "budget_end" {
  description = "Last day the account must last (shown in the weekly email)."
  type        = string
  default     = "2026-11-14"
}

provider "aws" {
  region  = var.region
  profile = var.aws_profile
  default_tags {
    tags = { Project = "receipt-flow", Environment = "dev", ManagedBy = "terraform" }
  }
}

locals {
  name = "receipt-flow-dev"
}

# ── budget alarms: actual spend passes $50 / $100 / $150, or the forecast passes the budget ──────────

# Two budgets (names as the team uses them in the console). DO NOT RENAME them: a console-made budget
# report (Budgets → Budget reports, no API for it) points at these names; renaming replaces the budget
# and silently drops the report.
#   "aws-team4-receipt-flow" — this project, counted from when the team started (2026-10-01); alarms and
#                            the weekly email use this one
#   "aws-team4"              — the whole account for the calendar year (it includes usage from before the
#                            team), for reference only
resource "aws_budgets_budget" "team" {
  name              = "aws-team4-receipt-flow"
  budget_type       = "COST"
  limit_amount      = tostring(var.budget_usd)
  limit_unit        = "USD"
  time_unit         = "CUSTOM" # counts only between the two dates (an ANNUALLY budget counts the calendar year)
  time_period_start = "${var.project_start}_00:00"
  time_period_end   = "${var.budget_end}_23:59"

  dynamic "notification" {
    for_each = [50, 100, 150]
    content {
      comparison_operator        = "GREATER_THAN"
      threshold                  = notification.value
      threshold_type             = "ABSOLUTE_VALUE"
      notification_type          = "ACTUAL"
      subscriber_email_addresses = var.report_emails
    }
  }

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    notification_type          = "FORECASTED"
    subscriber_email_addresses = var.report_emails
  }
}

resource "aws_budgets_budget" "account_year" {
  name         = "aws-team4"
  budget_type  = "COST"
  limit_amount = tostring(var.budget_usd)
  limit_unit   = "USD"
  time_unit    = "ANNUALLY"
}

data "aws_caller_identity" "current" {}

# last week's yearly total, so the report can show the change since then
resource "aws_ssm_parameter" "last_total" {
  name  = "/receipt-flow/cost-report/last-year-total"
  type  = "String"
  value = "none"
  lifecycle {
    ignore_changes = [value] # the Lambda updates it every week
  }
}

# ── weekly cost email ────────────────────────────────────────────────────────────────────────────────

resource "aws_sns_topic" "cost_report" {
  name = "${local.name}-cost-report"
}

resource "aws_sns_topic_subscription" "cost_report" {
  for_each  = toset(var.report_emails)
  topic_arn = aws_sns_topic.cost_report.arn
  protocol  = "email"
  endpoint  = each.value
}

data "archive_file" "cost_report" {
  type        = "zip"
  source_file = "${path.module}/lambda/cost_report.py"
  output_path = "${path.module}/.build/cost_report.zip"
}

data "aws_iam_policy_document" "lambda_trust" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

data "aws_iam_policy_document" "cost_report" {
  statement {
    actions   = ["budgets:ViewBudget"]
    resources = ["arn:aws:budgets::${data.aws_caller_identity.current.account_id}:budget/*"]
  }
  statement {
    actions   = ["ssm:GetParameter", "ssm:PutParameter"]
    resources = [aws_ssm_parameter.last_total.arn]
  }
  statement {
    sid = "SeeWhatIsRunning"
    actions = [
      "eks:ListClusters", "ec2:DescribeInstances", "ec2:DescribeNatGateways", "ec2:DescribeAddresses",
      "elasticloadbalancing:DescribeLoadBalancers",
    ]
    resources = ["*"]
  }
  statement {
    actions   = ["sns:Publish"]
    resources = [aws_sns_topic.cost_report.arn]
  }
  statement {
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.cost_report.arn}:*"]
  }
}

resource "aws_iam_role" "cost_report" {
  name               = "${local.name}-cost-report"
  assume_role_policy = data.aws_iam_policy_document.lambda_trust.json
}

resource "aws_iam_role_policy" "cost_report" {
  role   = aws_iam_role.cost_report.id
  policy = data.aws_iam_policy_document.cost_report.json
}

resource "aws_cloudwatch_log_group" "cost_report" {
  name              = "/aws/lambda/${local.name}-cost-report"
  retention_in_days = 14
}

resource "aws_lambda_function" "cost_report" {
  function_name    = "${local.name}-cost-report"
  role             = aws_iam_role.cost_report.arn
  runtime          = "python3.13"
  handler          = "cost_report.handler"
  filename         = data.archive_file.cost_report.output_path
  source_code_hash = data.archive_file.cost_report.output_base64sha256
  timeout          = 30
  environment {
    variables = {
      TOPIC_ARN      = aws_sns_topic.cost_report.arn
      ACCOUNT_ID     = data.aws_caller_identity.current.account_id
      PROJECT_BUDGET = aws_budgets_budget.team.name
      LAST_PARAM     = aws_ssm_parameter.last_total.name
      BUDGET_USD     = tostring(var.budget_usd)
      BUDGET_END     = var.budget_end
      START          = var.project_start
    }
  }
  depends_on = [aws_cloudwatch_log_group.cost_report]
}

# Mondays 00:00 UTC = 09:00 KST
resource "aws_cloudwatch_event_rule" "weekly" {
  name                = "${local.name}-cost-report-weekly"
  schedule_expression = "cron(0 0 ? * MON *)"
}

resource "aws_cloudwatch_event_target" "weekly" {
  rule = aws_cloudwatch_event_rule.weekly.name
  arn  = aws_lambda_function.cost_report.arn
}

resource "aws_lambda_permission" "weekly" {
  statement_id  = "weekly-schedule"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.cost_report.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.weekly.arn
}

output "send_now" {
  description = "Send the report right away (e.g. after confirming the subscription)."
  value       = "aws lambda invoke --function-name ${aws_lambda_function.cost_report.function_name} --profile ${var.aws_profile} --region ${var.region} out.json"
}
