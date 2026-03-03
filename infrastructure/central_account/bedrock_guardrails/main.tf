# SSM Parameter to store consolidated guardrail configuration for ECS
resource "aws_ssm_parameter" "guardrail_config" {
  name        = "/${var.common.environment}/guardrails/config"
  description = "Consolidated guardrail configuration from all shared accounts for ${var.common.environment}"
  type        = "SecureString"
  key_id      = var.kms_key_arn
  value       = jsonencode({})
  tags        = var.tags
}
