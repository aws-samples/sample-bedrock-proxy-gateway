# Observability Module

This module provisions observability infrastructure for the Bedrock Proxy Gateway:

## Resources Created

- S3 bucket for observability data storage with KMS encryption
- Kinesis streams for logs, metrics, and traces with KMS encryption
- IAM policy for accessing observability resources
- KMS key for encryption of all observability resources

## Key Features

- Environment-specific deployment (only for dev, qa, prod)
- Encrypted storage and streaming with KMS
- Proper IAM permissions for ECS tasks
- Integration with OTEL collector for telemetry data

## Environment Variables Added to Containers

- `OBSERVABILITY_S3_BUCKET`: S3 bucket name for observability data
- `KINESIS_LOGS_STREAM`: Kinesis stream name for logs
- `KINESIS_METRICS_STREAM`: Kinesis stream name for metrics
- `KINESIS_TRACES_STREAM`: Kinesis stream name for traces

## Naming Convention

- S3 bucket: `s3-{account_id}-{environment}-{service}-observability`
- Kinesis streams: `{env_prefix}{app_id}-{environment}-{service}-{signal}`
- Resources are only created for dev, qa, and prod environments

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
| [aws_cloudwatch_log_group.bedrock_logs](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/cloudwatch_log_group) | resource |
| [aws_cloudwatch_log_resource_policy.cross_account_logs](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/cloudwatch_log_resource_policy) | resource |
| [aws_iam_policy.observability_access](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/iam_policy) | resource |
| [aws_kms_alias.observability](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/kms_alias) | resource |
| [aws_kms_key.observability](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/kms_key) | resource |
| [aws_s3_bucket.observability](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/s3_bucket) | resource |
| [aws_s3_bucket_lifecycle_configuration.observability](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/s3_bucket_lifecycle_configuration) | resource |
| [aws_s3_bucket_public_access_block.observability](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/s3_bucket_public_access_block) | resource |
| [aws_s3_bucket_server_side_encryption_configuration.observability](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/s3_bucket_server_side_encryption_configuration) | resource |

## Inputs

| Name | Description | Type | Default | Required |
|------|-------------|------|---------|:--------:|
| <a name="input_common"></a> [common](#input\_common) | Common variables shared across all modules | <pre>object({<br/>    app_id             = string<br/>    aws_region         = string<br/>    aws_account_id     = string<br/>    environment        = string<br/>    service_name       = string<br/>    log_retention_days = number<br/>  })</pre> | n/a | yes |
| <a name="input_common_tags"></a> [common\_tags](#input\_common\_tags) | Common tags applied to all resources | `map(string)` | n/a | yes |
| <a name="input_shared_account_ids"></a> [shared\_account\_ids](#input\_shared\_account\_ids) | Comma-separated list of shared account IDs for cross-account log access | `string` | n/a | yes |

## Outputs

| Name | Description |
|------|-------------|
| <a name="output_bedrock_logs_group_arn"></a> [bedrock\_logs\_group\_arn](#output\_bedrock\_logs\_group\_arn) | ARN of the central CloudWatch Log Group for Bedrock model invocations |
| <a name="output_observability_kms_key_arn"></a> [observability\_kms\_key\_arn](#output\_observability\_kms\_key\_arn) | ARN of KMS key used for S3 and CloudWatch Logs encryption |
| <a name="output_observability_policy_arn"></a> [observability\_policy\_arn](#output\_observability\_policy\_arn) | ARN of the observability access policy |
| <a name="output_s3_bucket_name"></a> [s3\_bucket\_name](#output\_s3\_bucket\_name) | Name of the observability S3 bucket |
<!-- END_TF_DOCS -->
