# bedrock_guardrails

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
| [aws_ssm_parameter.guardrail_config](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/ssm_parameter) | resource |

## Inputs

| Name | Description | Type | Default | Required |
|------|-------------|------|---------|:--------:|
| <a name="input_common"></a> [common](#input\_common) | Common variables shared across all modules | <pre>object({<br/>    app_id             = string<br/>    aws_region         = string<br/>    aws_account_id     = string<br/>    environment        = string<br/>    service_name       = string<br/>    log_retention_days = number<br/>  })</pre> | n/a | yes |
| <a name="input_kms_key_arn"></a> [kms\_key\_arn](#input\_kms\_key\_arn) | ARN of the KMS key to use for SSM parameter encryption | `string` | n/a | yes |
| <a name="input_tags"></a> [tags](#input\_tags) | Common tags applied to all resources | `map(string)` | n/a | yes |

## Outputs

| Name | Description |
|------|-------------|
| <a name="output_guardrail_config_parameter_name"></a> [guardrail\_config\_parameter\_name](#output\_guardrail\_config\_parameter\_name) | Name of the SSM parameter containing consolidated guardrail configuration |
<!-- END_TF_DOCS -->
