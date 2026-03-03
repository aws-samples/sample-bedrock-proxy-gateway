output "bedrock_logging_role_arn" {
  description = "ARN of the Bedrock logging role"
  value       = aws_iam_role.bedrock_logging_role.arn
}

output "bedrock_guardrails" {
  description = "Map of guardrail logical IDs to their configurations"
  value = jsonencode({
    for profile_name, profile_config in local.guardrail_profiles :
    profile_name => {
      guardrail_id = aws_bedrock_guardrail.bedrock_guardrails[profile_name].guardrail_id
      version      = aws_bedrock_guardrail_version.bedrock_guadrail_versions[profile_name].version
    }
  })
}
