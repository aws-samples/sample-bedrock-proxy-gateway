# OIDC Federation Outputs
output "oidc_provider_arn" {
  description = "ARN of the OIDC provider"
  value       = module.oidc_federation.oidc_provider_arn
}

# IAM Role Outputs
output "federation_role_arn" {
  description = "ARN of the federation IAM role"
  value       = module.iam_role.role_arn
}

output "federation_role_name" {
  description = "Name of the federation IAM role"
  value       = module.iam_role.role_name
}

# CloudWatch KMS Outputs
output "kms_key_arn" {
  description = "ARN of the KMS key for CloudWatch logs"
  value       = module.cloudwatch_kms.kms_key_arn
}

output "log_group_name" {
  description = "Name of the CloudWatch log group"
  value       = module.cloudwatch_kms.log_group_name
}

# Bedrock Guardrails Outputs
output "bedrock_logging_role_arn" {
  description = "ARN of the Bedrock logging role"
  value       = module.bedrock_guardrails.bedrock_logging_role_arn
}

output "bedrock_guardrails" {
  description = "List of all deployed guardrails with their logical names"
  value       = module.bedrock_guardrails.bedrock_guardrails
}
