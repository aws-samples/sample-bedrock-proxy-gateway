output "consolidated_guardrails_ssm_parameter" {
  description = "SSM parameter name containing consolidated guardrails configuration"
  value       = aws_ssm_parameter.consolidated_guardrails.name
}

output "consolidated_guardrails_config" {
  description = "Consolidated guardrails configuration"
  value       = local.consolidated_guardrails
  sensitive   = false
}
