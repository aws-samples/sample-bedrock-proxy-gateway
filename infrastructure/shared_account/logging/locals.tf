locals {
  # Construct the base name prefix using environment and AppId
  name_prefix = "${var.common.app_id}-${var.common.environment}"

  # Create the final resource name by combining prefix and service
  resource_name = "${local.name_prefix}-${var.common.service_name}"

  logs_destination_arn = "arn:aws:logs:${var.common.aws_region}:${var.central_account_id}:destination:${local.resource_name}-bedrock-logs-destination"

  filter_role_arn = "arn:aws:sts::${var.common.aws_account_id}:assumed-role/${var.filter_role_name}/*"
}
