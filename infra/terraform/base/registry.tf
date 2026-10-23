# ECR repositories.
# IAM policies and roles live in ../admin.

locals {
  images = ["api-service", "chat-service", "preprocess-service", "ocr-worker", "web"]
}

resource "aws_ecr_repository" "svc" {
  for_each             = toset(local.images)
  name                 = "${var.project}/${each.value}"
  image_tag_mutability = "MUTABLE"
  force_delete         = true
  image_scanning_configuration {
    scan_on_push = true
  }
}

resource "aws_ecr_lifecycle_policy" "svc" {
  for_each   = aws_ecr_repository.svc
  repository = each.value.name
  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "keep last 10 images"
      selection    = { tagStatus = "any", countType = "imageCountMoreThan", countNumber = 10 }
      action       = { type = "expire" }
    }]
  })
}

# Budget alarms and the weekly cost email live in ../ops (emails stay out of git).
