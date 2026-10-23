# S3 (receipt images) → SQS (analysis queue) and the DynamoDB single table.

resource "aws_s3_bucket" "receipts" {
  bucket        = "${local.name}-receipts-${local.account_id}"
  force_destroy = true
}

resource "aws_s3_bucket_public_access_block" "receipts" {
  bucket                  = aws_s3_bucket.receipts.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "receipts" {
  bucket = aws_s3_bucket.receipts.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_cors_configuration" "receipts" {
  bucket = aws_s3_bucket.receipts.id
  cors_rule {
    allowed_methods = ["PUT", "GET"]
    allowed_origins = var.web_origins
    allowed_headers = ["Content-Type"]
    max_age_seconds = 3000
  }
}

resource "aws_sqs_queue" "analysis_dlq" {
  name                      = "${local.name}-analysis-dlq"
  message_retention_seconds = 1209600
  sqs_managed_sse_enabled   = true
}

resource "aws_sqs_queue" "analysis" {
  name                       = "${local.name}-analysis"
  visibility_timeout_seconds = 180
  receive_wait_time_seconds  = 20
  message_retention_seconds  = 86400
  sqs_managed_sse_enabled    = true
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.analysis_dlq.arn
    maxReceiveCount     = 3
  })
}

data "aws_iam_policy_document" "analysis_queue" {
  statement {
    actions   = ["sqs:SendMessage"]
    resources = [aws_sqs_queue.analysis.arn]
    principals {
      type        = "Service"
      identifiers = ["s3.amazonaws.com"]
    }
    condition {
      test     = "ArnEquals"
      variable = "aws:SourceArn"
      values   = [aws_s3_bucket.receipts.arn]
    }
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [local.account_id]
    }
  }
}

resource "aws_sqs_queue_policy" "analysis" {
  queue_url = aws_sqs_queue.analysis.id
  policy    = data.aws_iam_policy_document.analysis_queue.json
}

resource "aws_s3_bucket_notification" "incoming" {
  bucket = aws_s3_bucket.receipts.id
  queue {
    queue_arn     = aws_sqs_queue.analysis.arn
    events        = ["s3:ObjectCreated:*"]
    filter_prefix = "incoming/"
    filter_suffix = ".jpg"
  }
  depends_on = [aws_sqs_queue_policy.analysis]
}

resource "aws_dynamodb_table" "main" {
  name         = local.name
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "pk"
  range_key    = "sk"

  dynamic "attribute" {
    for_each = ["pk", "sk", "gsi1pk", "gsi1sk", "gsi2pk", "gsi2sk"]
    content {
      name = attribute.value
      type = "S"
    }
  }

  global_secondary_index {
    name            = "gsi1"
    hash_key        = "gsi1pk"
    range_key       = "gsi1sk"
    projection_type = "ALL"
  }

  global_secondary_index {
    name            = "gsi2"
    hash_key        = "gsi2pk"
    range_key       = "gsi2sk"
    projection_type = "ALL"
  }
}
