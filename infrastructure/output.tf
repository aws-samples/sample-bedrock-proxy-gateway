# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

output "bedrock_vpc_endpoint" {
  description = "Bedrock VPC Endpoint"
  value       = module.central_account.bedrock_vpc_endpoint
}

output "bedrock_runtime_vpc_endpoint" {
  description = "Bedrock Runtime VPC Endpoint"
  value       = module.central_account.bedrock_runtime_vpc_endpoint
}

output "sts_vpc_endpoint" {
  description = "STS VPC Endpoint"
  value       = module.central_account.sts_vpc_endpoint_id
}

output "restricted_role_session_name_suffix" {
  description = "Restricted Role Session Name Suffix"
  value       = module.central_account.restricted_role_session_name_suffix
}

output "consolidated_guardrails_ssm_parameter" {
  description = "SSM parameter name containing consolidated guardrails configuration"
  value       = module.guardrail_consolidation.consolidated_guardrails_ssm_parameter
}

output "consolidated_guardrails_config" {
  description = "Consolidated guardrails configuration"
  value       = module.guardrail_consolidation.consolidated_guardrails_config
  sensitive   = true
}
