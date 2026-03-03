# Compute Module

This module provisions ECS infrastructure with OTEL observability:

## Resources Created
- ECS Fargate cluster and service
- Task definition with API container and AWS OTEL Collector sidecar
- IAM roles for Bedrock and observability access
- CloudWatch log groups for application and OTEL logs
- Security group for ECS

## Key Features
- OpenTelemetry integration with AWS X-Ray and CloudWatch
- Bedrock API access for AI workloads
- Container insights enabled
- Health checks and circuit breaker deployment
- Integrates with ALB from networking module

<!-- BEGIN_TF_DOCS -->
## Requirements

No requirements.

## Providers

| Name | Version |
|------|---------|
| <a name="provider_aws"></a> [aws](#provider\_aws) | n/a |
| <a name="provider_random"></a> [random](#provider\_random) | n/a |

## Modules

No modules.

## Resources

| Name | Type |
|------|------|
| [aws_appautoscaling_policy.ecs_scale_cpu](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/appautoscaling_policy) | resource |
| [aws_appautoscaling_policy.ecs_scale_memory](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/appautoscaling_policy) | resource |
| [aws_appautoscaling_policy.ecs_scale_queue_depth](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/appautoscaling_policy) | resource |
| [aws_appautoscaling_policy.ecs_scale_request_rate](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/appautoscaling_policy) | resource |
| [aws_appautoscaling_policy.ecs_scale_response_time](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/appautoscaling_policy) | resource |
| [aws_appautoscaling_target.ecs_target](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/appautoscaling_target) | resource |
| [aws_cloudwatch_log_group.api_otel_logs_group](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/cloudwatch_log_group) | resource |
| [aws_cloudwatch_log_group.ecs_logs](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/cloudwatch_log_group) | resource |
| [aws_cloudwatch_log_group.otel_collector_logs](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/cloudwatch_log_group) | resource |
| [aws_ecs_cluster.api_cluster](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/ecs_cluster) | resource |
| [aws_ecs_service.api_service](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/ecs_service) | resource |
| [aws_ecs_task_definition.api_task](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/ecs_task_definition) | resource |
| [aws_iam_policy.elasticache_policy](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/iam_policy) | resource |
| [aws_iam_policy.observability_policy](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/iam_policy) | resource |
| [aws_iam_policy.ssm_config_policy](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/iam_policy) | resource |
| [aws_iam_role.ecs_execution_role](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/iam_role) | resource |
| [aws_iam_role.ecs_task_role](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/iam_role) | resource |
| [aws_iam_role_policy_attachment.ecs_execution_cloudwatch_policy](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/iam_role_policy_attachment) | resource |
| [aws_iam_role_policy_attachment.ecs_execution_policy](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/iam_role_policy_attachment) | resource |
| [aws_iam_role_policy_attachment.ecs_execution_ssm_config_policy](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/iam_role_policy_attachment) | resource |
| [aws_iam_role_policy_attachment.ecs_task_elasticache_policy](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/iam_role_policy_attachment) | resource |
| [aws_iam_role_policy_attachment.ecs_task_observability_access_policy](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/iam_role_policy_attachment) | resource |
| [aws_iam_role_policy_attachment.ecs_task_observability_policy](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/iam_role_policy_attachment) | resource |
| [aws_kms_alias.logs_key_alias](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/kms_alias) | resource |
| [aws_kms_key.logs_key](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/kms_key) | resource |
| [aws_security_group.ecs_sg](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/security_group) | resource |
| [random_string.restricted_role_session_name_suffix](https://registry.terraform.io/providers/hashicorp/random/latest/docs/resources/string) | resource |

## Inputs

| Name | Description | Type | Default | Required |
|------|-------------|------|---------|:--------:|
| <a name="input_alb_security_group_id"></a> [alb\_security\_group\_id](#input\_alb\_security\_group\_id) | ALB security group ID from networking module | `string` | n/a | yes |
| <a name="input_alb_target_group_arn"></a> [alb\_target\_group\_arn](#input\_alb\_target\_group\_arn) | ALB target group ARN from networking module | `string` | n/a | yes |
| <a name="input_bedrock_runtime_vpc_endpoint_dns"></a> [bedrock\_runtime\_vpc\_endpoint\_dns](#input\_bedrock\_runtime\_vpc\_endpoint\_dns) | Bedrock VPC Endpoint DNS name | `string` | `""` | no |
| <a name="input_common"></a> [common](#input\_common) | Common variables shared across all modules | <pre>object({<br/>    app_id             = string<br/>    aws_region         = string<br/>    aws_account_id     = string<br/>    environment        = string<br/>    service_name       = string<br/>    log_retention_days = number<br/>  })</pre> | n/a | yes |
| <a name="input_common_tags"></a> [common\_tags](#input\_common\_tags) | Common tags applied to all resources | `map(string)` | n/a | yes |
| <a name="input_environment_config"></a> [environment\_config](#input\_environment\_config) | Environment-specific configuration from root variables | <pre>object({<br/>    log_retention             = number<br/>    ecs_task_cpu              = number<br/>    ecs_task_memory           = number<br/>    ecs_service_desired_count = number<br/>  })</pre> | n/a | yes |
| <a name="input_gw_api_image_tag"></a> [gw\_api\_image\_tag](#input\_gw\_api\_image\_tag) | Docker image tag for the Bedrock Gateway API to deploy | `string` | n/a | yes |
| <a name="input_jwt_allowed_scopes"></a> [jwt\_allowed\_scopes](#input\_jwt\_allowed\_scopes) | Comma-separated list of allowed JWT scopes | `string` | n/a | yes |
| <a name="input_jwt_audience"></a> [jwt\_audience](#input\_jwt\_audience) | Expected JWT audience claim | `string` | n/a | yes |
| <a name="input_oauth_issuer"></a> [oauth\_issuer](#input\_oauth\_issuer) | OAuth token issuer | `string` | n/a | yes |
| <a name="input_oauth_jwks_url"></a> [oauth\_jwks\_url](#input\_oauth\_jwks\_url) | OAuth JWKS URL for JWT token validation | `string` | n/a | yes |
| <a name="input_observability_policy_arn"></a> [observability\_policy\_arn](#input\_observability\_policy\_arn) | ARN of the observability access policy | `string` | `""` | no |
| <a name="input_oidc_role_name"></a> [oidc\_role\_name](#input\_oidc\_role\_name) | Name of the IAM role for the OIDC provider | `string` | n/a | yes |
| <a name="input_private_subnet_ids"></a> [private\_subnet\_ids](#input\_private\_subnet\_ids) | List of private subnet IDs for resource deployment | `list(string)` | n/a | yes |
| <a name="input_s3_bucket_name"></a> [s3\_bucket\_name](#input\_s3\_bucket\_name) | Name of the observability S3 bucket | `string` | `""` | no |
| <a name="input_shared_account_ids"></a> [shared\_account\_ids](#input\_shared\_account\_ids) | List of shared account IDs for resource access | `string` | n/a | yes |
| <a name="input_sts_vpc_endpoint_dns"></a> [sts\_vpc\_endpoint\_dns](#input\_sts\_vpc\_endpoint\_dns) | STS VPC Endpoint DNS name | `string` | `""` | no |
| <a name="input_valkey_endpoint_address"></a> [valkey\_endpoint\_address](#input\_valkey\_endpoint\_address) | Valkey cache endpoint address | `string` | `""` | no |
| <a name="input_valkey_endpoint_port"></a> [valkey\_endpoint\_port](#input\_valkey\_endpoint\_port) | Valkey cache endpoint port | `string` | `""` | no |
| <a name="input_vpc_cidr_block"></a> [vpc\_cidr\_block](#input\_vpc\_cidr\_block) | VPC CIDR block for security group rules | `string` | n/a | yes |
| <a name="input_vpc_id"></a> [vpc\_id](#input\_vpc\_id) | VPC ID where resources will be deployed | `string` | n/a | yes |

## Outputs

| Name | Description |
|------|-------------|
| <a name="output_ecs_cluster_name"></a> [ecs\_cluster\_name](#output\_ecs\_cluster\_name) | Name of the ECS cluster |
| <a name="output_ecs_service_name"></a> [ecs\_service\_name](#output\_ecs\_service\_name) | Name of the ECS service |
| <a name="output_restricted_role_session_name_suffix"></a> [restricted\_role\_session\_name\_suffix](#output\_restricted\_role\_session\_name\_suffix) | IAM role trust policy within shared accounts enforces this suffix for all AssumeRoleWWI calls |
<!-- END_TF_DOCS -->
