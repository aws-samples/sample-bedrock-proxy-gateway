locals {
  # Construct the base name prefix using environment and AppId
  name_prefix = "${var.common.app_id}-${var.common.environment}"

  # Create the final resource name by combining prefix and service
  resource_name = "${local.name_prefix}-${var.common.service_name}"

  # ECR resource names
  ecr_repository_name = "ecr-${local.resource_name}"

  # ECS resource names
  ecs_cluster_name           = "ecs-${local.resource_name}"
  ecs_task_definition_family = "ecs-td-${local.resource_name}"
  ecs_service_name           = var.common.service_name
  api_container_name         = "${local.ecs_service_name}-api"
  otel_collector_name        = "${local.ecs_service_name}-otel-collector"
  security_group_name        = "sec-gp-${local.resource_name}-ecs"
  ecs_container_insight_log  = "${local.resource_name}--cluster/performance"

  # IAM resource names
  ecs_execution_role_name   = "iam-rol-${local.resource_name}-ecs-execution"
  ecs_task_role_name        = "iam-rol-${local.resource_name}-ecs-task"
  observability_policy_name = "iam-pol-${local.resource_name}-observability"

  # Otel ECR Image path
  otle_ecr_image_path = "${var.common.aws_account_id}.dkr.ecr.${var.common.aws_region}.amazonaws.com/${var.common.app_id}-${var.common.environment}-otel-collector:latest"

  # CloudWatch Log Group names
  log_groups = {
    ecs            = "/aws/ecs/${local.resource_name}-api"
    otel_collector = "/aws/ecs/${local.resource_name}-otel-collector"
    logs_group     = "${local.resource_name}-logs"
  }

  # KMS resource names
  kms_key_description = "KMS key for CloudWatch logs encryption"
  kms_alias_name      = "alias/${local.resource_name}-logs-key"

  otel_collector_config = "${path.module}/otel-collector-config.yaml"

  # Extract app hash from image tag (format: account.dkr.ecr.region.amazonaws.com/repo:timestamp-apphash)
  app_hash = length(split(":", var.gw_api_image_tag)) > 1 && length(split("-", split(":", var.gw_api_image_tag)[1])) > 2 ? split("-", split(":", var.gw_api_image_tag)[1])[2] : "unknown"

  # Valkey cache name
  valkey_cache_name = "vlk-${local.name_prefix}"

}
