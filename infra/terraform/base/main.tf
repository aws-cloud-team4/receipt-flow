# Always-on, low-cost resources: storage, queue, auth, image registry, IAM policies.
# EKS (hourly cost) lives in ../eks and is created only for integration/demo weeks.

terraform {
  required_version = ">= 1.11"
  backend "s3" {
    bucket       = "receipt-flow-tfstate-431777499129"
    key          = "base/terraform.tfstate"
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

provider "aws" {
  region  = var.region
  profile = var.aws_profile
  default_tags {
    tags = {
      Project     = var.project
      Environment = var.env
      ManagedBy   = "terraform"
    }
  }
}

data "aws_caller_identity" "current" {}

locals {
  name       = "${var.project}-${var.env}"
  account_id = data.aws_caller_identity.current.account_id
}
