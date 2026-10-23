# IAM stack, kept apart from ../base so permission changes are reviewed on their own.
#
# Contents: S3 image expiry, per-service IAM policies, and the IAM roles EKS will need
# (cluster, nodes, one Pod Identity role per service). Reads ../base outputs from its local state.

terraform {
  required_version = ">= 1.11"
  backend "s3" {
    bucket       = "receipt-flow-tfstate-431777499129"
    key          = "admin/terraform.tfstate"
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
  description = "Local AWS CLI profile of a team IAM user (never root)."
  type        = string
}

variable "image_retention_days" {
  description = "Receipt photos contain personal data; delete them automatically after this many days."
  type        = number
  default     = 90
}

provider "aws" {
  region  = var.region
  profile = var.aws_profile
  default_tags {
    tags = { Project = "receipt-flow", Environment = "dev", ManagedBy = "terraform" }
  }
}

data "terraform_remote_state" "base" {
  backend = "s3"
  config = {
    bucket  = "receipt-flow-tfstate-431777499129"
    key     = "base/terraform.tfstate"
    region  = "ap-northeast-2"
    profile = "team-admin"
  }
}

data "aws_caller_identity" "current" {}

locals {
  base       = data.terraform_remote_state.base.outputs
  name       = "receipt-flow-dev"
  account_id = data.aws_caller_identity.current.account_id
}

resource "aws_s3_bucket_lifecycle_configuration" "receipts" {
  bucket = local.base.bucket
  rule {
    id     = "expire-receipt-images"
    status = "Enabled"
    filter {}
    expiration {
      days = var.image_retention_days
    }
    abort_incomplete_multipart_upload {
      days_after_initiation = 1
    }
  }
}
