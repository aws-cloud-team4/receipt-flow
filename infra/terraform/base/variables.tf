variable "project" {
  type    = string
  default = "receipt-flow"
}

variable "env" {
  type    = string
  default = "dev"
}

variable "region" {
  type    = string
  default = "ap-northeast-2"
}

variable "aws_profile" {
  description = "Local AWS CLI profile. Set to null in CI (OIDC credentials come from the environment)."
  type        = string
  default     = "team-admin"
}

variable "web_origins" {
  description = "Browser origins allowed to upload to S3 (presigned PUT). The EKS ALB and the CloudFront (HTTPS) addresses are only known once they exist, so their patterns are allowed."
  type        = list(string)
  default     = ["http://localhost:*", "http://*.ap-northeast-2.elb.amazonaws.com", "https://*.ap-northeast-2.elb.amazonaws.com", "https://*.cloudfront.net"]
}

