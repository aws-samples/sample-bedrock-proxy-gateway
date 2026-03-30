# iam_role

<!-- BEGIN_TF_DOCS -->
## Requirements

No requirements.

## Providers

| Name | Version |
|------|---------|
| <a name="provider_aws"></a> [aws](#provider\_aws) | n/a |

## Modules

No modules.

## Resources

| Name | Type |
|------|------|
| [aws_iam_role.oauth_federation_role](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/iam_role) | resource |
| [aws_iam_role_policy.oauth_bedrock_access](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/iam_role_policy) | resource |

## Inputs

| Name | Description | Type | Default | Required |
|------|-------------|------|---------|:--------:|
| <a name="input_allowed_source_vpc_endpoint_ids"></a> [allowed\_source\_vpc\_endpoint\_ids](#input\_allowed\_source\_vpc\_endpoint\_ids) | ID of the source VPC endpoint allowed to use IAM role credentials | `list(string)` | `null` | no |
| <a name="input_aws_account_id"></a> [aws\_account\_id](#input\_aws\_account\_id) | AWS Account ID | `string` | n/a | yes |
| <a name="input_environment"></a> [environment](#input\_environment) | Environment name | `string` | n/a | yes |
| <a name="input_jwt_audience"></a> [jwt\_audience](#input\_jwt\_audience) | JWT audience for OIDC provider | `string` | `"BPG"` | no |
| <a name="input_oidc_provider_arn"></a> [oidc\_provider\_arn](#input\_oidc\_provider\_arn) | ARN of the OIDC provider | `string` | n/a | yes |
| <a name="input_oidc_provider_url"></a> [oidc\_provider\_url](#input\_oidc\_provider\_url) | URL of the OIDC provider | `string` | n/a | yes |
| <a name="input_restricted_role_session_name_suffix"></a> [restricted\_role\_session\_name\_suffix](#input\_restricted\_role\_session\_name\_suffix) | Suffix to append to a role session name to restrict ARWWI calls with JWT | `string` | `null` | no |
| <a name="input_role_name"></a> [role\_name](#input\_role\_name) | Name of the IAM role for the OIDC provider | `string` | n/a | yes |
| <a name="input_tags"></a> [tags](#input\_tags) | Tags to apply to resources | `map(string)` | `{}` | no |

## Outputs

| Name | Description |
|------|-------------|
| <a name="output_role_arn"></a> [role\_arn](#output\_role\_arn) | ARN of the created IAM role |
| <a name="output_role_name"></a> [role\_name](#output\_role\_name) | Name of the created IAM role |
<!-- END_TF_DOCS -->
