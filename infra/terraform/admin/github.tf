# GitHub Actions → AWS without long-lived keys. Set github_repo ("owner/name") to enable.

variable "github_repo" {
  description = "GitHub repository allowed to deploy (owner/name). Empty = no deploy role (an apply with \"\" deletes it)."
  type        = string
  default     = "aws-cloud-team4/receipt-flow"
}

# The team repo uses GitHub's immutable OIDC subject: sub = "repo:<owner>@<owner id>/<name>@<repo id>:…".
# Value: gh api repos/<owner>/<name>/actions/oidc/customization/sub → sub_claim_prefix. Empty = plain repo:<owner>/<name>.
variable "github_sub_prefix" {
  type    = string
  default = "repo:aws-cloud-team4@340943354/receipt-flow@1420632042"
}

locals {
  github      = var.github_repo != "" ? 1 : 0
  github_subs = distinct(compact(["repo:${var.github_repo}", var.github_sub_prefix]))
}

resource "aws_iam_openid_connect_provider" "github" {
  count          = local.github
  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]
}

data "aws_iam_policy_document" "github_trust" {
  count = local.github
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github[0].arn]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }
    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      values   = flatten([for p in local.github_subs : ["${p}:ref:refs/heads/main", "${p}:environment:demo"]])
    }
  }
}

data "aws_iam_policy_document" "github_deploy" {
  count = local.github
  statement {
    actions   = ["ecr:GetAuthorizationToken", "eks:DescribeCluster"]
    resources = ["*"]
  }
  statement {
    actions = [
      "ecr:BatchCheckLayerAvailability", "ecr:InitiateLayerUpload", "ecr:UploadLayerPart",
      "ecr:CompleteLayerUpload", "ecr:PutImage", "ecr:BatchGetImage",
    ]
    resources = ["arn:aws:ecr:${var.region}:${local.account_id}:repository/receipt-flow/*"]
  }
}

resource "aws_iam_role" "github_deploy" {
  count              = local.github
  name               = "${local.name}-github-deploy"
  assume_role_policy = data.aws_iam_policy_document.github_trust[0].json
}

resource "aws_iam_role_policy" "github_deploy" {
  count  = local.github
  role   = aws_iam_role.github_deploy[0].id
  policy = data.aws_iam_policy_document.github_deploy[0].json
}

output "github_deploy_role_arn" {
  description = "Put in the repo secret AWS_DEPLOY_ROLE_ARN. The eks stack gives it cluster access automatically."
  value       = one(aws_iam_role.github_deploy[*].arn)
}
