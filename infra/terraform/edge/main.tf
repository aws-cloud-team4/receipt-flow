# HTTPS in front of the EKS ALB: a CloudFront distribution with its own *.cloudfront.net address,
# so phones get https:// without buying a domain. Free tier at our traffic; costs nothing while idle,
# so it stays between deploys and the address never changes. deploy/deploy.sh points it at the new ALB:
#   terraform -chdir=infra/terraform/edge apply -var aws_profile=team-admin -var alb_dns_name=<ALB host>
# While the cluster is down the address answers 502.

terraform {
  required_version = ">= 1.11"
  backend "s3" {
    bucket       = "receipt-flow-tfstate-431777499129"
    key          = "edge/terraform.tfstate"
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

variable "aws_profile" {
  type    = string
  default = null
}

variable "alb_dns_name" {
  description = "Hostname of the ingress ALB (kubectl -n receipt-flow get ingress receipt-flow)."
  type        = string
}

provider "aws" {
  region  = "ap-northeast-2"
  profile = var.aws_profile
  default_tags {
    tags = { Project = "receipt-flow", Environment = "dev", ManagedBy = "terraform" }
  }
}

data "aws_cloudfront_cache_policy" "disabled" {
  name = "Managed-CachingDisabled"
}

data "aws_cloudfront_cache_policy" "optimized" {
  name = "Managed-CachingOptimized"
}

# Everything the viewer sent (Authorization, query strings, cookies) except Host, which stays the ALB's.
data "aws_cloudfront_origin_request_policy" "all_viewer" {
  name = "Managed-AllViewerExceptHostHeader"
}

resource "aws_cloudfront_distribution" "web" {
  enabled         = true
  comment         = "receipt-flow: HTTPS in front of the EKS ALB"
  price_class     = "PriceClass_200"
  http_version    = "http2and3"
  is_ipv6_enabled = true

  origin {
    origin_id   = "alb"
    domain_name = var.alb_dns_name
    custom_origin_config {
      http_port              = 80
      https_port             = 443
      origin_protocol_policy = "http-only"
      origin_ssl_protocols   = ["TLSv1.2"]
      # Longest gap allowed between bytes without a quota increase; chat streams (SSE) keep sending.
      origin_read_timeout = 60
    }
  }

  # API, chat (SSE) and the SPA's index.html: never cached, passed through as is.
  default_cache_behavior {
    target_origin_id         = "alb"
    viewer_protocol_policy   = "redirect-to-https"
    allowed_methods          = ["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"]
    cached_methods           = ["GET", "HEAD"]
    cache_policy_id          = data.aws_cloudfront_cache_policy.disabled.id
    origin_request_policy_id = data.aws_cloudfront_origin_request_policy.all_viewer.id
    compress                 = false
  }

  # Vite's hashed bundles never change under the same name.
  ordered_cache_behavior {
    path_pattern           = "/assets/*"
    target_origin_id       = "alb"
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD"]
    cached_methods         = ["GET", "HEAD"]
    cache_policy_id        = data.aws_cloudfront_cache_policy.optimized.id
    compress               = true
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = true
  }
}

output "url" {
  value = "https://${aws_cloudfront_distribution.web.domain_name}"
}
