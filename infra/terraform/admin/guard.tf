# Guard rails for the team's IAM users. Everyone keeps AdministratorAccess (CLI and local development
# work as before); these deny policies only block the accidents that would hurt the whole team:
#   1. destroying the shared resources (table, buckets, queues, user pool, image repositories)
#   2. going outside Seoul for the costly services, or launching large instances
#   3. changing IAM (users, roles, policies) — except for var.iam_admins
# An explicit Deny beats AdministratorAccess. To really delete a shared resource, set
# guard_enabled = false, apply, do it, and set it back the same day.

variable "team_users" {
  description = "Team IAM users the guard applies to."
  type        = list(string)
  default     = ["chahee", "junyoung", "subin", "taehee"]
}

variable "iam_admins" {
  description = "Team users who may still change IAM (the infra owner and the project lead)."
  type        = list(string)
  default     = ["chahee", "junyoung"]
}

variable "guard_enabled" {
  description = "false only while deliberately deleting a shared resource (break glass), then back to true."
  type        = bool
  default     = true
}

variable "allowed_instance_types" {
  description = "EC2 instance types the team may launch (EKS nodes included)."
  type        = list(string)
  default     = ["t3.*", "t3a.*", "t4g.*"]
}

locals {
  arn_prefix = "arn:aws"
  shared = {
    table  = "${local.arn_prefix}:dynamodb:${var.region}:${local.account_id}:table/receipt-flow-*"
    bucket = "${local.arn_prefix}:s3:::receipt-flow-*"
    queue  = "${local.arn_prefix}:sqs:${var.region}:${local.account_id}:receipt-flow-*"
    pool   = "${local.arn_prefix}:cognito-idp:${var.region}:${local.account_id}:userpool/*"
    repo   = "${local.arn_prefix}:ecr:${var.region}:${local.account_id}:repository/receipt-flow/*"
  }
}

data "aws_iam_policy_document" "guard_shared" {
  statement {
    sid    = "NoDestroyingSharedResources"
    effect = "Deny"
    actions = [
      "dynamodb:DeleteTable",
      "s3:DeleteBucket",
      "s3:DeleteBucketPolicy",
      "sqs:DeleteQueue",
      "sqs:PurgeQueue",
      "cognito-idp:DeleteUserPool",
      "cognito-idp:DeleteUserPoolClient",
      "cognito-idp:DeleteGroup",
      "cognito-idp:DeleteUserPoolDomain",
      "ecr:DeleteRepository",
    ]
    resources = values(local.shared)
  }

  statement {
    sid       = "StateHistoryStaysOn"
    effect    = "Deny"
    actions   = ["s3:PutBucketVersioning", "s3:PutLifecycleConfiguration"]
    resources = ["${local.arn_prefix}:s3:::receipt-flow-tfstate-*"]
  }

  statement {
    sid    = "CostlyServicesOnlyInSeoul"
    effect = "Deny"
    actions = [
      "ec2:RunInstances",
      "ec2:CreateNatGateway",
      "eks:CreateCluster",
      "rds:CreateDBInstance",
      "rds:CreateDBCluster",
      "elasticloadbalancing:CreateLoadBalancer",
      "lambda:CreateFunction",
      "ecs:CreateCluster",
      "s3:CreateBucket",
      "dynamodb:CreateTable",
      "es:CreateDomain",
      "elasticache:CreateCacheCluster",
      "elasticache:CreateReplicationGroup",
      "redshift:CreateCluster",
      "lightsail:CreateInstances",
    ]
    resources = ["*"]
    condition {
      test     = "StringNotEquals"
      variable = "aws:RequestedRegion"
      values   = [var.region]
    }
  }

  statement {
    sid       = "SmallInstancesOnly"
    effect    = "Deny"
    actions   = ["ec2:RunInstances"]
    resources = ["${local.arn_prefix}:ec2:*:*:instance/*"]
    condition {
      test     = "StringNotLike"
      variable = "ec2:InstanceType"
      values   = var.allowed_instance_types
    }
  }

  statement {
    sid       = "NoMachineLearningClusters"
    effect    = "Deny"
    actions   = ["sagemaker:Create*"]
    resources = ["*"]
  }
}

data "aws_iam_policy_document" "guard_iam" {
  statement {
    sid    = "NoIamChanges"
    effect = "Deny"
    actions = [
      "iam:CreateUser", "iam:DeleteUser", "iam:UpdateUser",
      "iam:CreateRole", "iam:DeleteRole", "iam:UpdateRole", "iam:UpdateAssumeRolePolicy",
      "iam:CreatePolicy", "iam:CreatePolicyVersion", "iam:DeletePolicy", "iam:DeletePolicyVersion",
      "iam:SetDefaultPolicyVersion",
      "iam:AttachUserPolicy", "iam:DetachUserPolicy", "iam:PutUserPolicy", "iam:DeleteUserPolicy",
      "iam:AttachRolePolicy", "iam:DetachRolePolicy", "iam:PutRolePolicy", "iam:DeleteRolePolicy",
      "iam:AttachGroupPolicy", "iam:DetachGroupPolicy", "iam:PutGroupPolicy", "iam:DeleteGroupPolicy",
      "iam:AddUserToGroup", "iam:RemoveUserFromGroup",
      "iam:PutUserPermissionsBoundary", "iam:DeleteUserPermissionsBoundary",
      "iam:PutRolePermissionsBoundary", "iam:DeleteRolePermissionsBoundary",
      "iam:CreateOpenIDConnectProvider", "iam:DeleteOpenIDConnectProvider",
    ]
    resources = ["*"]
  }

  statement {
    sid           = "NoChangingOtherPeoplesLogins"
    effect        = "Deny"
    actions       = ["iam:CreateLoginProfile", "iam:UpdateLoginProfile", "iam:DeleteLoginProfile", "iam:CreateAccessKey", "iam:DeleteAccessKey", "iam:UpdateAccessKey"]
    not_resources = ["${local.arn_prefix}:iam::${local.account_id}:user/$${aws:username}"]
  }
}

resource "aws_iam_policy" "guard_shared" {
  name        = "receipt-flow-team-guard"
  description = "Deny destroying shared resources, costly services outside Seoul, large instances."
  policy      = data.aws_iam_policy_document.guard_shared.json
}

resource "aws_iam_policy" "guard_iam" {
  name        = "receipt-flow-team-guard-iam"
  description = "Deny IAM changes and touching other people's logins."
  policy      = data.aws_iam_policy_document.guard_iam.json
}

resource "aws_iam_user_policy_attachment" "guard_shared" {
  for_each   = var.guard_enabled ? toset(var.team_users) : toset([])
  user       = each.value
  policy_arn = aws_iam_policy.guard_shared.arn
}

resource "aws_iam_user_policy_attachment" "guard_iam" {
  for_each   = toset([for u in var.team_users : u if !contains(var.iam_admins, u)])
  user       = each.value
  policy_arn = aws_iam_policy.guard_iam.arn
}
