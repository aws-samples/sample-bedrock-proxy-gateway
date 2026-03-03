output "kms_key_arn" {
  description = "ARN of the KMS key"
  value       = aws_kms_key.bedrock_logs_key.arn
}

output "kms_key_id" {
  description = "ID of the KMS key"
  value       = aws_kms_key.bedrock_logs_key.key_id
}

output "log_group_name" {
  description = "Name of the CloudWatch log group"
  value       = length(aws_cloudwatch_log_group.bedrock_logs) > 0 ? aws_cloudwatch_log_group.bedrock_logs[0].name : var.log_group_name
}

output "log_group_arn" {
  description = "ARN of the CloudWatch log group"
  value       = length(aws_cloudwatch_log_group.bedrock_logs) > 0 ? aws_cloudwatch_log_group.bedrock_logs[0].arn : "arn:aws:logs:${data.aws_region.current.id}:${var.central_account_id}:log-group:${var.log_group_name}"
}

data "aws_region" "current" {}
