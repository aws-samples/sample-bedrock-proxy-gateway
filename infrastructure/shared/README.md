# shared

<!-- BEGIN_TF_DOCS -->
## Requirements

| Name | Version |
|------|---------|
| <a name="requirement_terraform"></a> [terraform](#requirement\_terraform) | >=1.12.2, <2.0.0 |
| <a name="requirement_aws"></a> [aws](#requirement\_aws) | ~>6.0.0 |

## Providers

| Name | Version |
|------|---------|
| <a name="provider_aws"></a> [aws](#provider\_aws) | ~>6.0.0 |
| <a name="provider_aws.central"></a> [aws.central](#provider\_aws.central) | ~>6.0.0 |

## Modules

| Name | Source | Version |
|------|--------|---------|
| <a name="module_shared_account"></a> [shared\_account](#module\_shared\_account) | ../modules/bedrock_access | n/a |

## Resources

| Name | Type |
|------|------|
| [aws_caller_identity.shared](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/data-sources/caller_identity) | data source |
| [aws_ssm_parameter.bedrock_runtime_vpce_id](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/data-sources/ssm_parameter) | data source |
| [aws_ssm_parameter.bedrock_vpce_id](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/data-sources/ssm_parameter) | data source |

## Inputs

| Name | Description | Type | Default | Required |
|------|-------------|------|---------|:--------:|
| <a name="input_additional_tags"></a> [additional\_tags](#input\_additional\_tags) | n/a | `map(string)` | `{}` | no |
| <a name="input_app_id"></a> [app\_id](#input\_app\_id) | n/a | `string` | `"myapp"` | no |
| <a name="input_aws_region"></a> [aws\_region](#input\_aws\_region) | n/a | `string` | n/a | yes |
| <a name="input_central_account_id"></a> [central\_account\_id](#input\_central\_account\_id) | n/a | `string` | n/a | yes |
| <a name="input_central_account_profile"></a> [central\_account\_profile](#input\_central\_account\_profile) | n/a | `string` | `"default"` | no |
| <a name="input_environment"></a> [environment](#input\_environment) | n/a | `string` | n/a | yes |
| <a name="input_environment_config"></a> [environment\_config](#input\_environment\_config) | n/a | <pre>map(object({<br/>    ecs_desired_count = number<br/>    ecs_cpu           = number<br/>    ecs_memory        = number<br/>    domain_prefix     = string<br/>    log_retention     = number<br/>  }))</pre> | <pre>{<br/>  "dev": {<br/>    "domain_prefix": "dev",<br/>    "ecs_cpu": 2048,<br/>    "ecs_desired_count": 1,<br/>    "ecs_memory": 4096,<br/>    "log_retention": 7<br/>  },<br/>  "test": {<br/>    "domain_prefix": "test",<br/>    "ecs_cpu": 4096,<br/>    "ecs_desired_count": 4,<br/>    "ecs_memory": 8192,<br/>    "log_retention": 120<br/>  }<br/>}</pre> | no |
| <a name="input_gw_api_image_tag"></a> [gw\_api\_image\_tag](#input\_gw\_api\_image\_tag) | n/a | `string` | `""` | no |
| <a name="input_jwt_allowed_scopes"></a> [jwt\_allowed\_scopes](#input\_jwt\_allowed\_scopes) | n/a | `string` | `""` | no |
| <a name="input_jwt_audience"></a> [jwt\_audience](#input\_jwt\_audience) | n/a | `string` | `""` | no |
| <a name="input_mtls_cert_ca_s3_path"></a> [mtls\_cert\_ca\_s3\_path](#input\_mtls\_cert\_ca\_s3\_path) | n/a | `string` | `""` | no |
| <a name="input_oauth_issuer"></a> [oauth\_issuer](#input\_oauth\_issuer) | n/a | `string` | `""` | no |
| <a name="input_oauth_jwks_url"></a> [oauth\_jwks\_url](#input\_oauth\_jwks\_url) | n/a | `string` | `""` | no |
| <a name="input_restricted_role_session_name_suffix"></a> [restricted\_role\_session\_name\_suffix](#input\_restricted\_role\_session\_name\_suffix) | n/a | `string` | `null` | no |
| <a name="input_service_name"></a> [service\_name](#input\_service\_name) | n/a | `string` | `"bedrock-proxy-gateway"` | no |
| <a name="input_shared_account_ids"></a> [shared\_account\_ids](#input\_shared\_account\_ids) | n/a | `string` | `""` | no |
| <a name="input_shared_account_profile"></a> [shared\_account\_profile](#input\_shared\_account\_profile) | n/a | `string` | `"default"` | no |

## Outputs

No outputs.
<!-- END_TF_DOCS -->
