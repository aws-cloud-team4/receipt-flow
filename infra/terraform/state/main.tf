# The S3 bucket that holds every other stack's Terraform state, so any teammate can plan/apply
# (lock files live next to the state: S3 native locking, no DynamoDB table).
# This stack keeps its own tiny state locally; it is created once and rarely changes.
#   terraform -chdir=infra/terraform/state init && terraform -chdir=infra/terraform/state apply

terraform {
  required_version = ">= 1.11"
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
  type    = string
  default = "team-admin"
}

provider "aws" {
  region  = var.region
  profile = var.aws_profile
  default_tags {
    tags = { Project = "receipt-flow", Environment = "dev", ManagedBy = "terraform" }
  }
}

data "aws_caller_identity" "current" {}

resource "aws_s3_bucket" "state" {
  bucket = "receipt-flow-tfstate-${data.aws_caller_identity.current.account_id}"
  lifecycle {
    prevent_destroy = true # losing it means losing track of every resource
  }
}

resource "aws_s3_bucket_versioning" "state" {
  bucket = aws_s3_bucket.state.id
  versioning_configuration {
    status = "Enabled" # an overwritten or deleted state can be restored
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "state" {
  bucket = aws_s3_bucket.state.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "state" {
  bucket                  = aws_s3_bucket.state.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

output "bucket" {
  value = aws_s3_bucket.state.bucket
}
