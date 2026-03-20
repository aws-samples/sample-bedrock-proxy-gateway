# Container Insights Module

This module enables CloudWatch Container Insights at the account level for ECS clusters.

## Resources Created

- **AWS CloudWatch Account Settings**: Enables Container Insights at the account level

## Features

- Automatically collects metrics for CPU, memory, disk, and network usage
- Provides visibility into container performance and health
- Enables detailed monitoring of ECS tasks and services
- Supports troubleshooting and optimization of containerized applications

## Usage

This module is automatically included in the central account deployment for dev, qa, and prod environments.

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
| [aws_ecs_account_setting_default.container_insights](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/ecs_account_setting_default) | resource |

## Inputs

| Name | Description | Type | Default | Required |
|------|-------------|------|---------|:--------:|
| <a name="input_common"></a> [common](#input\_common) | Common variables shared across all modules | <pre>object({<br/>    app_id             = string<br/>    aws_region         = string<br/>    aws_account_id     = string<br/>    environment        = string<br/>    service_name       = string<br/>    log_retention_days = number<br/>  })</pre> | n/a | yes |
| <a name="input_common_tags"></a> [common\_tags](#input\_common\_tags) | Common tags applied to all resources | `map(string)` | n/a | yes |

## Outputs

No outputs.
<!-- END_TF_DOCS -->
