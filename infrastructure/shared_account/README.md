# shared_account

<!-- BEGIN_TF_DOCS -->
## Requirements

| Name | Version |
|------|---------|
| <a name="requirement_aws"></a> [aws](#requirement\_aws) | ~>6.0.0 |

## Providers

No providers.

## Modules

| Name | Source | Version |
|------|--------|---------|
| <a name="module_bedrock_guardrails"></a> [bedrock\_guardrails](#module\_bedrock\_guardrails) | ./bedrock_guardrails | n/a |
| <a name="module_cloudwatch_kms"></a> [cloudwatch\_kms](#module\_cloudwatch\_kms) | ./cloudwatch_kms | n/a |
| <a name="module_iam_role"></a> [iam\_role](#module\_iam\_role) | ./iam_role | n/a |
| <a name="module_logging"></a> [logging](#module\_logging) | ./logging | n/a |
| <a name="module_oidc_federation"></a> [oidc\_federation](#module\_oidc\_federation) | ./oidc_federation | n/a |

## Resources

No resources.

## Inputs

| Name | Description | Type | Default | Required |
|------|-------------|------|---------|:--------:|
| <a name="input_bedrock_runtime_vpce_id"></a> [bedrock\_runtime\_vpce\_id](#input\_bedrock\_runtime\_vpce\_id) | Bedrock VPC Endpoint ID | `string` | `""` | no |
| <a name="input_bedrock_vpce_id"></a> [bedrock\_vpce\_id](#input\_bedrock\_vpce\_id) | Bedrock VPC Endpoint ID | `string` | `""` | no |
| <a name="input_central_account_id"></a> [central\_account\_id](#input\_central\_account\_id) | List of central account ID for resource access | `string` | n/a | yes |
| <a name="input_common"></a> [common](#input\_common) | Common variables shared across all modules | <pre>object({<br/>    app_id             = string<br/>    aws_region         = string<br/>    aws_account_id     = string<br/>    environment        = string<br/>    service_name       = string<br/>    log_retention_days = number<br/>  })</pre> | n/a | yes |
| <a name="input_common_tags"></a> [common\_tags](#input\_common\_tags) | Common tags applied to all resources | `map(string)` | n/a | yes |
| <a name="input_jwt_audience"></a> [jwt\_audience](#input\_jwt\_audience) | JWT audience for OIDC provider | `string` | `"BPG"` | no |
| <a name="input_oauth_provider_url"></a> [oauth\_provider\_url](#input\_oauth\_provider\_url) | OAuth provider URL (e.g., 'https://your-oauth-provider.com') | `string` | n/a | yes |
| <a name="input_oidc_role_name"></a> [oidc\_role\_name](#input\_oidc\_role\_name) | Name of the IAM role for the OIDC provider | `string` | n/a | yes |
| <a name="input_restricted_role_session_name_suffix"></a> [restricted\_role\_session\_name\_suffix](#input\_restricted\_role\_session\_name\_suffix) | Suffix to append to a role session name to restrict ARWWI calls with JWT | `string` | `null` | no |

## Outputs

| Name | Description |
|------|-------------|
| <a name="output_bedrock_guardrails"></a> [bedrock\_guardrails](#output\_bedrock\_guardrails) | List of all deployed guardrails with their logical names |
| <a name="output_bedrock_logging_role_arn"></a> [bedrock\_logging\_role\_arn](#output\_bedrock\_logging\_role\_arn) | ARN of the Bedrock logging role |
| <a name="output_federation_role_arn"></a> [federation\_role\_arn](#output\_federation\_role\_arn) | ARN of the federation IAM role |
| <a name="output_federation_role_name"></a> [federation\_role\_name](#output\_federation\_role\_name) | Name of the federation IAM role |
| <a name="output_kms_key_arn"></a> [kms\_key\_arn](#output\_kms\_key\_arn) | ARN of the KMS key for CloudWatch logs |
| <a name="output_log_group_name"></a> [log\_group\_name](#output\_log\_group\_name) | Name of the CloudWatch log group |
| <a name="output_oidc_provider_arn"></a> [oidc\_provider\_arn](#output\_oidc\_provider\_arn) | ARN of the OIDC provider |
<!-- END_TF_DOCS -->
