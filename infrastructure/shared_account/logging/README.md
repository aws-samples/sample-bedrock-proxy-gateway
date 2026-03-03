# Shared Account Logging Module

This module creates the logging infrastructure in shared accounts to forward Bedrock model invocation logs to the central account's Kinesis stream.

## Resources Created

- **CloudWatch Logs Subscription Filter**: Forwards logs from `/aws/bedrock/modelinvocations` to central account
- **IAM Role**: Allows CloudWatch Logs service to write to central account's Kinesis stream
- **IAM Policy**: Grants permissions to put records into the Kinesis stream

## Conditional Deployment

Resources are only created for production environments:
- `dev`
- `qa`
- `preprod`
- `prod`

For other environments (like personal workspaces), no resources are created.

## Architecture

```
Shared Account                    Central Account
┌─────────────────────────────┐   ┌──────────────────┐
│ /aws/bedrock/modelinvocations│   │                  │
│            │                │   │                  │
│            ▼                │   │                  │
│ Subscription Filter         │───┼─→ Kinesis Stream │
│            │                │   │                  │
│            │                │   │                  │
│ IAM Role (CloudWatch Logs)  │   │                  │
└─────────────────────────────┘   └──────────────────┘
```

## Filter Configuration

- **Log Group**: `/aws/bedrock/modelinvocations` (AWS managed)
- **Filter Pattern**: `""` (captures ALL log events)
- **Destination**: Central account Kinesis stream (cross-account)

## Cross-Account Permissions

The IAM role in this shared account has permissions to:
- `kinesis:PutRecord` - Send individual log events
- `kinesis:PutRecords` - Send batch log events

## Outputs

- `cloudwatch_logs_kinesis_role_arn`: ARN of the IAM role used by CloudWatch Logs service

## Usage

This module is automatically included in shared account deployments when the central account Kinesis stream ARN is provided.

<!-- BEGIN_TF_DOCS -->
## Requirements

No requirements.

## Providers

No providers.

## Modules

No modules.

## Resources

No resources.

## Inputs

| Name | Description | Type | Default | Required |
|------|-------------|------|---------|:--------:|
| <a name="input_central_account_id"></a> [central\_account\_id](#input\_central\_account\_id) | Central account ID for cross-account resource access | `string` | n/a | yes |
| <a name="input_common"></a> [common](#input\_common) | Common variables shared across all modules | <pre>object({<br/>    app_id             = string<br/>    aws_region         = string<br/>    aws_account_id     = string<br/>    environment        = string<br/>    service_name       = string<br/>    log_retention_days = number<br/>  })</pre> | n/a | yes |
| <a name="input_common_tags"></a> [common\_tags](#input\_common\_tags) | Common tags applied to all resources | `map(string)` | n/a | yes |
| <a name="input_filter_role_name"></a> [filter\_role\_name](#input\_filter\_role\_name) | ARN of the IAM role to filter Bedrock logs by (only logs from this role will be forwarded) | `string` | n/a | yes |

## Outputs

No outputs.
<!-- END_TF_DOCS -->
