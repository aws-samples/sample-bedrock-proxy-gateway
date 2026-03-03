terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.83.0"
    }
  }
}

# Read all guardrail registry entries from shared accounts
data "aws_ssm_parameters_by_path" "guardrail_registry" {
  path = "/${var.common.service_name}/${var.common.environment}/guardrails/account"
}

locals {
  # Parse all account guardrails from SSM
  account_guardrails = {
    for name, value in zipmap(
      data.aws_ssm_parameters_by_path.guardrail_registry.names,
      data.aws_ssm_parameters_by_path.guardrail_registry.values
    ) :
    # Extract account ID from path: /service/env/guardrails/account/123456 -> 123456
    element(split("/", name), length(split("/", name)) - 1) => jsondecode(value)
  }

  # Consolidate guardrails by logical ID across all accounts
  consolidated_guardrails = {
    for logical_id in distinct(flatten([
      for account_id, guardrails in local.account_guardrails :
      keys(guardrails)
    ])) :
    logical_id => {
      for account_id, guardrails in local.account_guardrails :
      account_id => guardrails[logical_id]
      if contains(keys(guardrails), logical_id)
    }
  }
}

# Store consolidated guardrail configuration in central account SSM
resource "aws_ssm_parameter" "consolidated_guardrails" {
  #checkov:skip=CKV2_AWS_34: "Parameter contains guardrail configuration mappings, not secrets"
  name  = "/${var.common.service_name}/${var.common.environment}/guardrails/consolidated-config"
  type  = "String"
  value = jsonencode(local.consolidated_guardrails)

  tags = merge(var.common_tags, {
    Name        = "${var.common.service_name}-consolidated-guardrails"
    Environment = var.common.environment
  })
}
