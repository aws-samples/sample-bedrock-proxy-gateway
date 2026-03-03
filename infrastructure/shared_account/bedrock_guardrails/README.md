# Bedrock Guardrails Module

This module creates AWS Bedrock Guardrails for content filtering and security policies.

## Guardrails Created

### 1. Baseline Security Guardrail
- **Purpose**: Full content filtering for general use cases
- **Content Filters**: HATE, INSULTS, SEXUAL, VIOLENCE, MISCONDUCT, PROMPT_ATTACK
- **Use Case**: Standard AI interactions requiring comprehensive content filtering

### 2. Comment Analysis Guardrail
- **Purpose**: Reduced content filtering for analyzing online comments
- **Content Filters**: SEXUAL, VIOLENCE, MISCONDUCT, PROMPT_ATTACK (excludes HATE and INSULTS)
- **Use Case**: Comment analysis where hate speech and insults need to be processed rather than blocked

## Features

- Contextual grounding with relevance threshold (0.7)
- Profanity filtering via managed word lists
- Versioned guardrails for production use
- SSM parameters for cross-account reference
- Proper tagging and resource naming

## Usage

The module is automatically deployed when the shared account infrastructure is applied.
Guardrail IDs and versions are stored in SSM parameters for reference by other services.

<!-- BEGIN_TF_DOCS -->
## Requirements

| Name | Version |
|------|---------|
| <a name="requirement_aws"></a> [aws](#requirement\_aws) | ~>6.0.0 |

## Providers

| Name | Version |
|------|---------|
| <a name="provider_aws"></a> [aws](#provider\_aws) | ~>6.0.0 |
| <a name="provider_aws.central"></a> [aws.central](#provider\_aws.central) | ~>6.0.0 |

## Modules

No modules.

## Resources

| Name | Type |
|------|------|
| [aws_bedrock_guardrail.bedrock_guardrails](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/bedrock_guardrail) | resource |
| [aws_bedrock_guardrail_version.bedrock_guadrail_versions](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/bedrock_guardrail_version) | resource |
| [aws_bedrock_model_invocation_logging_configuration.bedrock_logging](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/bedrock_model_invocation_logging_configuration) | resource |
| [aws_iam_role.bedrock_logging_role](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/iam_role) | resource |
| [aws_iam_role_policy.bedrock_logging_policy](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/iam_role_policy) | resource |
| [aws_ssm_parameter.guardrails_registry](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/ssm_parameter) | resource |

## Inputs

| Name | Description | Type | Default | Required |
|------|-------------|------|---------|:--------:|
| <a name="input_bedrock_logging_policy_name"></a> [bedrock\_logging\_policy\_name](#input\_bedrock\_logging\_policy\_name) | Name of the Bedrock logging IAM policy | `string` | n/a | yes |
| <a name="input_bedrock_logging_role_name"></a> [bedrock\_logging\_role\_name](#input\_bedrock\_logging\_role\_name) | Name of the Bedrock logging IAM role | `string` | n/a | yes |
| <a name="input_central_account_id"></a> [central\_account\_id](#input\_central\_account\_id) | Central account ID where logs are aggregated | `string` | n/a | yes |
| <a name="input_common"></a> [common](#input\_common) | Common variables shared across all modules | <pre>object({<br/>    app_id             = string<br/>    aws_region         = string<br/>    aws_account_id     = string<br/>    environment        = string<br/>    service_name       = string<br/>    log_retention_days = number<br/>  })</pre> | n/a | yes |
| <a name="input_log_group_name"></a> [log\_group\_name](#input\_log\_group\_name) | CloudWatch log group name for Bedrock | `string` | n/a | yes |
| <a name="input_tags"></a> [tags](#input\_tags) | Common tags applied to all resources | `map(string)` | n/a | yes |

## Outputs

| Name | Description |
|------|-------------|
| <a name="output_bedrock_guardrails"></a> [bedrock\_guardrails](#output\_bedrock\_guardrails) | Map of guardrail logical IDs to their configurations |
| <a name="output_bedrock_logging_role_arn"></a> [bedrock\_logging\_role\_arn](#output\_bedrock\_logging\_role\_arn) | ARN of the Bedrock logging role |
<!-- END_TF_DOCS -->
