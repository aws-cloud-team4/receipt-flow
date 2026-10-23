# Pod Identity roles for the two autoscalers of the final deploy (installed by `SCALING=1 deploy/deploy.sh`):
#   cluster-autoscaler (kube-system) adds/removes nodes in the managed node group (2 → 3)
#   keda-operator (keda) reads the analysis queue length to scale ocr-worker
# Roles cost nothing; they are only used while the cluster exists.

locals {
  cluster_name = "receipt-flow-dev" # infra/terraform/eks
}

data "aws_iam_policy_document" "cluster_autoscaler" {
  statement {
    sid       = "ResizeOnlyThisClustersNodeGroups"
    actions   = ["autoscaling:SetDesiredCapacity", "autoscaling:TerminateInstanceInAutoScalingGroup"]
    resources = ["*"]
    condition {
      test     = "StringEquals"
      variable = "aws:ResourceTag/k8s.io/cluster-autoscaler/${local.cluster_name}"
      values   = ["owned"]
    }
  }
  statement {
    sid = "Discover"
    actions = [
      "autoscaling:DescribeAutoScalingGroups",
      "autoscaling:DescribeAutoScalingInstances",
      "autoscaling:DescribeLaunchConfigurations",
      "autoscaling:DescribeScalingActivities",
      "autoscaling:DescribeTags",
      "ec2:DescribeImages",
      "ec2:DescribeInstanceTypes",
      "ec2:DescribeLaunchTemplateVersions",
      "ec2:GetInstanceTypesFromInstanceRequirements",
      "eks:DescribeNodegroup",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_policy" "cluster_autoscaler" {
  name   = "${local.name}-cluster-autoscaler"
  policy = data.aws_iam_policy_document.cluster_autoscaler.json
}

resource "aws_iam_role" "cluster_autoscaler" {
  name               = "${local.name}-cluster-autoscaler"
  assume_role_policy = data.aws_iam_policy_document.pod_identity_trust.json
}

resource "aws_iam_role_policy_attachment" "cluster_autoscaler" {
  role       = aws_iam_role.cluster_autoscaler.name
  policy_arn = aws_iam_policy.cluster_autoscaler.arn
}

data "aws_iam_policy_document" "keda" {
  statement {
    actions   = ["sqs:GetQueueAttributes"]
    resources = [local.base.queue_arn]
  }
}

resource "aws_iam_policy" "keda" {
  name   = "${local.name}-keda"
  policy = data.aws_iam_policy_document.keda.json
}

resource "aws_iam_role" "keda" {
  name               = "${local.name}-keda"
  assume_role_policy = data.aws_iam_policy_document.pod_identity_trust.json
}

resource "aws_iam_role_policy_attachment" "keda" {
  role       = aws_iam_role.keda.name
  policy_arn = aws_iam_policy.keda.arn
}

output "cluster_autoscaler_role_arn" {
  value = aws_iam_role.cluster_autoscaler.arn
}

output "keda_role_arn" {
  value = aws_iam_role.keda.arn
}
