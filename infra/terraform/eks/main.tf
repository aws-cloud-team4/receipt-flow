# EKS for integration/demo weeks only (~$0.10/h control plane + nodes + ALB + IPv4).
#   create:  terraform apply      destroy: terraform destroy  (then check ALB/EBS/ENI leftovers)
# Applied by an account admin: creating a cluster needs iam:PassRole, which the project guard denies.
# No NAT gateway: nodes sit in public subnets with public IPs (cost plan in the 기획서).

terraform {
  required_version = ">= 1.11"
  backend "s3" {
    bucket       = "receipt-flow-tfstate-431777499129"
    key          = "eks/terraform.tfstate"
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
  }
}

variable "region" {
  type    = string
  default = "ap-northeast-2"
}

variable "aws_profile" {
  type = string
}

variable "kubernetes_version" {
  description = "Use a standard-support version to avoid extended-support charges. Recheck support before deployment."
  type        = string
  default     = "1.35"
}

variable "node_instance_type" {
  type    = string
  default = "t3.medium"
}

variable "node_count" {
  description = "Nodes at creation. 1 = basic deploy (one t3.medium holds the app's ~15 pods). 2 = final deploy with the autoscalers (SCALING=1), which then grow to max 3."
  type        = number
  default     = 1
}

variable "node_min_count" {
  description = "Fewest nodes the Cluster Autoscaler keeps (max is 3). 2 during the demo so it never shrinks to 1 (the plan is 2-3 nodes)."
  type        = number
  default     = 1
  validation {
    condition     = var.node_min_count >= 1 && var.node_min_count <= 3
    error_message = "node_min_count must be 1-3."
  }
}

variable "admin_principal_arns" {
  description = "IAM users that get cluster-admin via EKS access entries (team members). The admin stack's GitHub deploy role is added automatically."
  type        = list(string)
  default     = []
}

provider "aws" {
  region  = var.region
  profile = var.aws_profile
  default_tags {
    tags = { Project = "receipt-flow", Environment = "dev", ManagedBy = "terraform" }
  }
}

data "terraform_remote_state" "admin" {
  backend = "s3"
  config = {
    bucket  = "receipt-flow-tfstate-431777499129"
    key     = "admin/terraform.tfstate"
    region  = "ap-northeast-2"
    profile = "team-admin"
  }
}

data "aws_availability_zones" "available" {
  state = "available"
}

locals {
  name  = "receipt-flow-dev"
  roles = data.terraform_remote_state.admin.outputs
  azs   = slice(data.aws_availability_zones.available.names, 0, 2)
  # GitHub Actions deploy role (admin stack, only when github_repo is set) runs kubectl too
  github_deploy_role = try(local.roles.github_deploy_role_arn, null)
  cluster_admins     = concat(var.admin_principal_arns, local.github_deploy_role == null ? [] : [local.github_deploy_role])
  # namespace/service-account → IAM role (EKS Pod Identity)
  pod_roles = merge(
    { for svc, arn in local.roles.service_role_arns : svc => { namespace = "receipt-flow", role = arn } },
    { aws-load-balancer-controller = { namespace = "kube-system", role = local.roles.alb_controller_role_arn } },
    # autoscalers of the final deploy (installed only with SCALING=1 deploy/deploy.sh)
    { for k, v in {
      cluster-autoscaler = { namespace = "kube-system", role = try(local.roles.cluster_autoscaler_role_arn, null) }
      keda-operator      = { namespace = "keda", role = try(local.roles.keda_role_arn, null) }
    } : k => v if v.role != null },
  )
}

# ── network ──────────────────────────────────────────────────────────────────

resource "aws_vpc" "main" {
  cidr_block           = "10.40.0.0/16"
  enable_dns_hostnames = true
  enable_dns_support   = true
  tags                 = { Name = local.name }
}

resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id
}

resource "aws_subnet" "public" {
  count                   = length(local.azs)
  vpc_id                  = aws_vpc.main.id
  availability_zone       = local.azs[count.index]
  cidr_block              = cidrsubnet(aws_vpc.main.cidr_block, 4, count.index)
  map_public_ip_on_launch = true
  tags = {
    Name                                  = "${local.name}-public-${count.index}"
    "kubernetes.io/role/elb"              = "1"
    "kubernetes.io/cluster/${local.name}" = "shared"
  }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main.id
  }
}

resource "aws_route_table_association" "public" {
  count          = length(aws_subnet.public)
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

# ── cluster ──────────────────────────────────────────────────────────────────

resource "aws_eks_cluster" "main" {
  name     = local.name
  version  = var.kubernetes_version
  role_arn = local.roles.eks_cluster_role_arn

  access_config {
    authentication_mode                         = "API"
    bootstrap_cluster_creator_admin_permissions = true
  }

  vpc_config {
    subnet_ids              = aws_subnet.public[*].id
    endpoint_public_access  = true
    endpoint_private_access = true
  }
}

resource "aws_eks_node_group" "default" {
  cluster_name    = aws_eks_cluster.main.name
  node_group_name = "default"
  node_role_arn   = local.roles.eks_node_role_arn
  subnet_ids      = aws_subnet.public[*].id
  instance_types  = [var.node_instance_type]
  capacity_type   = "ON_DEMAND"
  disk_size       = 20

  scaling_config {
    desired_size = var.node_count
    min_size     = var.node_min_count
    max_size     = 3
  }

  update_config {
    max_unavailable = 1
  }

  # the Cluster Autoscaler moves desired_size between min and max; Terraform must not reset it
  lifecycle {
    ignore_changes = [scaling_config[0].desired_size]
  }
}

resource "aws_eks_addon" "core" {
  for_each     = toset(["vpc-cni", "coredns", "kube-proxy", "eks-pod-identity-agent", "metrics-server"])
  cluster_name = aws_eks_cluster.main.name
  addon_name   = each.value
  depends_on   = [aws_eks_node_group.default]
}

resource "aws_eks_pod_identity_association" "svc" {
  for_each        = local.pod_roles
  cluster_name    = aws_eks_cluster.main.name
  namespace       = each.value.namespace
  service_account = each.key
  role_arn        = each.value.role
}

data "aws_caller_identity" "current" {}

# Whoever creates the cluster already gets admin (bootstrap_cluster_creator_admin_permissions),
# so they are skipped here; adding them twice fails with "access entry already in use".
resource "aws_eks_access_entry" "admin" {
  for_each      = toset([for arn in local.cluster_admins : arn if arn != data.aws_caller_identity.current.arn])
  cluster_name  = aws_eks_cluster.main.name
  principal_arn = each.value
}

resource "aws_eks_access_policy_association" "admin" {
  for_each      = aws_eks_access_entry.admin
  cluster_name  = aws_eks_cluster.main.name
  principal_arn = each.value.principal_arn
  policy_arn    = "arn:aws:eks::aws:cluster-access-policy/AmazonEKSClusterAdminPolicy"
  access_scope {
    type = "cluster"
  }
}

output "cluster_name" {
  value = aws_eks_cluster.main.name
}

output "vpc_id" {
  value = aws_vpc.main.id
}

output "kubeconfig_command" {
  value = "aws eks update-kubeconfig --region ${var.region} --name ${aws_eks_cluster.main.name}"
}
