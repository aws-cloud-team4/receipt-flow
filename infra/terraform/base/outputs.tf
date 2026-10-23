output "bucket" {
  value = aws_s3_bucket.receipts.bucket
}

output "queue_url" {
  value = aws_sqs_queue.analysis.url
}

output "table" {
  value = aws_dynamodb_table.main.name
}

output "cognito_pool_id" {
  value = aws_cognito_user_pool.main.id
}

output "cognito_client_id" {
  value = aws_cognito_user_pool_client.web.id
}

output "ecr_repositories" {
  value = { for k, r in aws_ecr_repository.svc : k => r.repository_url }
}

output "bucket_arn" {
  value = aws_s3_bucket.receipts.arn
}

output "queue_arn" {
  value = aws_sqs_queue.analysis.arn
}

output "table_arn" {
  value = aws_dynamodb_table.main.arn
}

# `terraform output -raw services_env > ../../../services/.env`
output "services_env" {
  value = <<-EOT
    RF_REGION=${var.region}
    RF_TABLE=${aws_dynamodb_table.main.name}
    RF_BUCKET=${aws_s3_bucket.receipts.bucket}
    RF_QUEUE_URL=${aws_sqs_queue.analysis.url}
    RF_AUTH_MODE=cognito
    RF_COGNITO_POOL_ID=${aws_cognito_user_pool.main.id}
    RF_COGNITO_CLIENT_ID=${aws_cognito_user_pool_client.web.id}
    RF_AI_MODE=bedrock
    RF_CORS_ORIGINS=${join(",", var.web_origins)}
    AWS_PROFILE=${coalesce(var.aws_profile, "default")}
  EOT
}

# `terraform output -raw web_env > ../../../web/.env.local`
output "web_env" {
  value = <<-EOT
    VITE_REGION=${var.region}
    VITE_COGNITO_CLIENT_ID=${aws_cognito_user_pool_client.web.id}
  EOT
}
