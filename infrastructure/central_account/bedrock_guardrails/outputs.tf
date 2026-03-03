output "guardrail_config_parameter_name" {
  description = "Name of the SSM parameter containing consolidated guardrail configuration"
  value       = aws_ssm_parameter.guardrail_config.name
}
