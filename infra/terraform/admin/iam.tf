# Least-privilege policy per service, attached to that service's Pod Identity role.

locals {
  table_arns = [local.base.table_arn, "${local.base.table_arn}/index/*"]
  ddb_rw     = ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:Query"]
  bedrock_invoke = {
    actions = ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"]
    # Cross-region / global inference profiles route to foundation models in other regions.
    resources = [
      "arn:aws:bedrock:*::foundation-model/*",
      "arn:aws:bedrock:*:${local.account_id}:inference-profile/*",
    ]
  }
  service_statements = {
    api-service = [
      { actions = local.ddb_rw, resources = local.table_arns },
      # deleting a draft and starting over after a new photo remove the receipt's items and chat
      { actions = ["dynamodb:DeleteItem", "dynamodb:BatchWriteItem"], resources = local.table_arns },
      {
        actions   = ["s3:PutObject", "s3:GetObject", "s3:DeleteObject"]
        resources = ["${local.base.bucket_arn}/*"]
      },
      # admin screen: accounts in the user pool (create, edit, temporary password, disable, role groups)
      {
        actions = [
          "cognito-idp:ListUsers", "cognito-idp:ListUsersInGroup", "cognito-idp:AdminGetUser",
          "cognito-idp:AdminCreateUser", "cognito-idp:AdminUpdateUserAttributes", "cognito-idp:AdminDeleteUserAttributes",
          "cognito-idp:AdminSetUserPassword", "cognito-idp:AdminDisableUser", "cognito-idp:AdminEnableUser", "cognito-idp:AdminDeleteUser",
          "cognito-idp:AdminListGroupsForUser", "cognito-idp:AdminAddUserToGroup", "cognito-idp:AdminRemoveUserFromGroup",
        ]
        resources = ["arn:aws:cognito-idp:${var.region}:${local.account_id}:userpool/${local.base.cognito_pool_id}"]
      },
      # landing page usage card: read the team budget once a day (Cost Explorer is blocked by the org)
      { actions = ["budgets:ViewBudget"], resources = ["arn:aws:budgets::${local.account_id}:budget/*"] },
    ]
    chat-service = [
      { actions = local.ddb_rw, resources = local.table_arns },
      local.bedrock_invoke,
    ]
    preprocess-service = [
      { actions = local.ddb_rw, resources = local.table_arns },
      {
        actions   = ["s3:GetObject", "s3:PutObject"]
        resources = ["${local.base.bucket_arn}/raw/*", "${local.base.bucket_arn}/incoming/*"]
      },
    ]
    ocr-worker = [
      { actions = local.ddb_rw, resources = local.table_arns },
      { actions = ["s3:GetObject"], resources = ["${local.base.bucket_arn}/incoming/*"] },
      {
        actions   = ["sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes", "sqs:ChangeMessageVisibility"]
        resources = [local.base.queue_arn]
      },
      local.bedrock_invoke,
    ]
  }
}

data "aws_iam_policy_document" "svc" {
  for_each = local.service_statements
  dynamic "statement" {
    for_each = each.value
    content {
      actions   = statement.value.actions
      resources = statement.value.resources
    }
  }
}

resource "aws_iam_policy" "svc" {
  for_each = data.aws_iam_policy_document.svc
  name     = "${local.name}-${each.key}"
  policy   = each.value.json
}

# ── roles for EKS (free to keep; the cluster itself is in ../eks) ─────────────

data "aws_iam_policy_document" "eks_cluster_trust" {
  statement {
    actions = ["sts:AssumeRole", "sts:TagSession"]
    principals {
      type        = "Service"
      identifiers = ["eks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "eks_cluster" {
  name               = "${local.name}-eks-cluster"
  assume_role_policy = data.aws_iam_policy_document.eks_cluster_trust.json
}

resource "aws_iam_role_policy_attachment" "eks_cluster" {
  role       = aws_iam_role.eks_cluster.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSClusterPolicy"
}

data "aws_iam_policy_document" "ec2_trust" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "eks_node" {
  name               = "${local.name}-eks-node"
  assume_role_policy = data.aws_iam_policy_document.ec2_trust.json
}

resource "aws_iam_role_policy_attachment" "eks_node" {
  for_each = toset([
    "arn:aws:iam::aws:policy/AmazonEKSWorkerNodePolicy",
    "arn:aws:iam::aws:policy/AmazonEKS_CNI_Policy",
    "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly",
  ])
  role       = aws_iam_role.eks_node.name
  policy_arn = each.value
}

data "aws_iam_policy_document" "pod_identity_trust" {
  statement {
    actions = ["sts:AssumeRole", "sts:TagSession"]
    principals {
      type        = "Service"
      identifiers = ["pods.eks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "svc" {
  for_each           = local.service_statements
  name               = "${local.name}-${each.key}"
  assume_role_policy = data.aws_iam_policy_document.pod_identity_trust.json
}

resource "aws_iam_role_policy_attachment" "svc" {
  for_each   = aws_iam_role.svc
  role       = each.value.name
  policy_arn = aws_iam_policy.svc[each.key].arn
}

# AWS Load Balancer Controller (ALB ingress). Policy JSON is the upstream one, vendored.
resource "aws_iam_policy" "alb_controller" {
  name   = "${local.name}-alb-controller"
  policy = file("${path.module}/alb-controller-policy.json")
}

resource "aws_iam_role" "alb_controller" {
  name               = "${local.name}-alb-controller"
  assume_role_policy = data.aws_iam_policy_document.pod_identity_trust.json
}

resource "aws_iam_role_policy_attachment" "alb_controller" {
  role       = aws_iam_role.alb_controller.name
  policy_arn = aws_iam_policy.alb_controller.arn
}

output "eks_cluster_role_arn" {
  value = aws_iam_role.eks_cluster.arn
}

output "eks_node_role_arn" {
  value = aws_iam_role.eks_node.arn
}

output "service_role_arns" {
  value = { for k, r in aws_iam_role.svc : k => r.arn }
}

output "alb_controller_role_arn" {
  value = aws_iam_role.alb_controller.arn
}
