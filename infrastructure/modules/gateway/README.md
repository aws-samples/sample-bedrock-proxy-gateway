# central_account

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
| <a name="module_caching"></a> [caching](#module\_caching) | ./caching | n/a |
| <a name="module_compute"></a> [compute](#module\_compute) | ./compute | n/a |
| <a name="module_container_insights"></a> [container\_insights](#module\_container\_insights) | ./container_insights | n/a |
| <a name="module_networking"></a> [networking](#module\_networking) | ./networking | n/a |
| <a name="module_observability"></a> [observability](#module\_observability) | ./observability | n/a |
| <a name="module_waf"></a> [waf](#module\_waf) | ./waf | n/a |

## Resources

No resources.

## Inputs

| Name | Description | Type | Default | Required |
|------|-------------|------|---------|:--------:|
| <a name="input_common"></a> [common](#input\_common) | Common variables shared across all modules | <pre>object({<br/>    app_id             = string<br/>    aws_region         = string<br/>    aws_account_id     = string<br/>    environment        = string<br/>    service_name       = string<br/>    log_retention_days = number<br/>  })</pre> | n/a | yes |
| <a name="input_common_tags"></a> [common\_tags](#input\_common\_tags) | Common tags applied to all resources | `map(string)` | n/a | yes |
| <a name="input_ecs_service_desired_count"></a> [ecs\_service\_desired\_count](#input\_ecs\_service\_desired\_count) | Desired number of ECS tasks (from environment config) | `number` | n/a | yes |
| <a name="input_ecs_task_cpu"></a> [ecs\_task\_cpu](#input\_ecs\_task\_cpu) | CPU units for ECS task (from environment config) | `number` | n/a | yes |
| <a name="input_ecs_task_memory"></a> [ecs\_task\_memory](#input\_ecs\_task\_memory) | Memory for ECS task in MiB (from environment config) | `number` | n/a | yes |
| <a name="input_gw_api_image_tag"></a> [gw\_api\_image\_tag](#input\_gw\_api\_image\_tag) | Docker image tag for the Bedrock Gateway API to deploy | `string` | n/a | yes |
| <a name="input_jwt_allowed_scopes"></a> [jwt\_allowed\_scopes](#input\_jwt\_allowed\_scopes) | Comma-separated list of allowed JWT scopes (e.g., bedrockproxygateway:read,bedrockproxygateway:invoke,bedrockproxygateway:admin) | `string` | n/a | yes |
| <a name="input_jwt_audience"></a> [jwt\_audience](#input\_jwt\_audience) | Expected JWT audience claim (must match aud in tokens) | `string` | n/a | yes |
| <a name="input_log_retention"></a> [log\_retention](#input\_log\_retention) | Log retention (from environment config) | `number` | n/a | yes |
| <a name="input_mtls_cert_ca_s3_path"></a> [mtls\_cert\_ca\_s3\_path](#input\_mtls\_cert\_ca\_s3\_path) | S3 URI path to the mTLS CA certificate | `string` | `""` | no |
| <a name="input_oauth_issuer"></a> [oauth\_issuer](#input\_oauth\_issuer) | OAuth token issuer (e.g., https://<tenant>.auth0.com/) | `string` | n/a | yes |
| <a name="input_oauth_jwks_url"></a> [oauth\_jwks\_url](#input\_oauth\_jwks\_url) | OAuth JWKS URL for JWT token validation (e.g., https://<tenant>.auth0.com/.well-known/jwks.json) | `string` | n/a | yes |
| <a name="input_oidc_role_name"></a> [oidc\_role\_name](#input\_oidc\_role\_name) | Name of the IAM role for the OIDC provider | `string` | n/a | yes |
| <a name="input_shared_account_ids"></a> [shared\_account\_ids](#input\_shared\_account\_ids) | List of shared account IDs for resource access | `string` | n/a | yes |

## Outputs

| Name | Description |
|------|-------------|
| <a name="output_bedrock_runtime_vpc_endpoint"></a> [bedrock\_runtime\_vpc\_endpoint](#output\_bedrock\_runtime\_vpc\_endpoint) | Bedrock Runtime VPC Endpoint |
| <a name="output_bedrock_vpc_endpoint"></a> [bedrock\_vpc\_endpoint](#output\_bedrock\_vpc\_endpoint) | Bedrock VPC Endpoint |
| <a name="output_ecs_alb_dns_name"></a> [ecs\_alb\_dns\_name](#output\_ecs\_alb\_dns\_name) | DNS name of the ECS ALB |
| <a name="output_ecs_cluster_name"></a> [ecs\_cluster\_name](#output\_ecs\_cluster\_name) | Name of the ECS cluster |
| <a name="output_ecs_service_name"></a> [ecs\_service\_name](#output\_ecs\_service\_name) | Name of the ECS service |
| <a name="output_observability_kms_key_arn"></a> [observability\_kms\_key\_arn](#output\_observability\_kms\_key\_arn) | ARN of KMS key used for S3 and CloudWatch Logs encryption |
| <a name="output_observability_s3_bucket_name"></a> [observability\_s3\_bucket\_name](#output\_observability\_s3\_bucket\_name) | Name of the observability S3 bucket |
| <a name="output_restricted_role_session_name_suffix"></a> [restricted\_role\_session\_name\_suffix](#output\_restricted\_role\_session\_name\_suffix) | n/a |
| <a name="output_sts_vpc_endpoint_id"></a> [sts\_vpc\_endpoint\_id](#output\_sts\_vpc\_endpoint\_id) | STS VPC Endpoint |
| <a name="output_valkey_endpoint"></a> [valkey\_endpoint](#output\_valkey\_endpoint) | Valkey cache endpoint |
<!-- END_TF_DOCS -->
