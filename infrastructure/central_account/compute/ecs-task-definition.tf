# This random string is generated one-time per deployment
# and is passed into the shared_accout module to restrict
# IAM role trust policy to allow AssumeRoleWWI calls only
# if session name parameter includes correct name suffix.
resource "random_string" "restricted_role_session_name_suffix" {
  length  = 16
  special = false
  upper   = false
  numeric = true
  lower   = true
  lifecycle {
    ignore_changes = all # the value won't change as long as resources exists in the state file
  }
}



resource "aws_ecs_task_definition" "api_task" {
  family                   = local.ecs_task_definition_family
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = var.environment_config.ecs_task_cpu
  memory                   = var.environment_config.ecs_task_memory
  execution_role_arn       = aws_iam_role.ecs_execution_role.arn
  task_role_arn            = aws_iam_role.ecs_task_role.arn

  container_definitions = jsonencode([
    {
      name      = local.api_container_name
      image     = var.gw_api_image_tag
      essential = true
      portMappings = [
        {
          containerPort = 8000
          hostPort      = 8000
          protocol      = "tcp"
        }
      ]
      environment = [
        {
          name  = "ENVIRONMENT"
          value = var.common.environment
        },
        {
          name  = "LOG_LEVEL"
          value = "WARNING"
        },
        {
          name  = "OTEL_SERVICE_NAME"
          value = var.common.service_name
        },
        {
          name  = "OTEL_EXPORTER_OTLP_ENDPOINT"
          value = "http://localhost:4317"
        },
        {
          name  = "SHARED_ACCOUNT_IDS"
          value = var.shared_account_ids
        },
        {
          name  = "SHARED_ROLE_NAME"
          value = var.oidc_role_name
        },
        {
          name  = "BEDROCK_RUNTIME_VPC_ENDPOINT_DNS"
          value = var.bedrock_runtime_vpc_endpoint_dns
        },
        {
          name  = "STS_VPC_ENDPOINT_DNS"
          value = var.sts_vpc_endpoint_dns
        },
        {
          name  = "OBSERVABILITY_S3_BUCKET"
          value = var.s3_bucket_name
        },
        {
          name  = "APP_HASH"
          value = local.app_hash
        },
        {
          name  = "STS_ROLE_SESSION_NAME_SUFFIX"
          value = random_string.restricted_role_session_name_suffix.result
        },
        {
          name  = "VALKEY_URL"
          value = "async+rediss://${var.valkey_endpoint_address}:${var.valkey_endpoint_port}"
        },
        {
          name  = "ELASTICACHE_CLUSTER_NAME"
          value = "vlk-${var.common.app_id}-${var.common.environment}"
        },
        {
          name  = "ELASTICACHE_USERNAME"
          value = "default"
        },
        {
          name  = "ELASTICACHE_USE_IAM"
          value = "true"
        },
        {
          name  = "RATE_LIMITING_ENABLED"
          value = "true"
        },
        {
          name  = "OAUTH_JWKS_URL"
          value = var.oauth_jwks_url
        },
        {
          name  = "OAUTH_ISSUER"
          value = var.oauth_issuer
        },
        {
          name  = "JWT_AUDIENCE"
          value = var.jwt_audience
        },
        {
          name  = "JWT_ALLOWED_SCOPES"
          value = var.jwt_allowed_scopes
        }
      ]
      healthCheck = {
        command     = ["CMD-SHELL", "curl -f http://localhost:8000/health || exit 1"]
        interval    = 30
        timeout     = 5
        retries     = 3
        startPeriod = 60
      }
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.ecs_logs.name
          "awslogs-region"        = var.common.aws_region
          "awslogs-stream-prefix" = "ecs"
        }
      }
      dependsOn = [
        {
          containerName = local.otel_collector_name
          condition     = "START"
        }
      ]
      # Container insights specific configurations
      # dockerLabels = {
      #   "com.amazonaws.ecs.container-insights" = "enabled"
      # }
    },
    {
      name      = local.otel_collector_name
      image     = local.otle_ecr_image_path
      essential = true
      cpu       = var.environment_config.ecs_task_cpu / 4
      memory    = var.environment_config.ecs_task_memory / 4
      command = [
        "--config=env:AOT_CONFIG_CONTENT"
      ]
      environment = [
        {
          name  = "AWS_REGION"
          value = var.common.aws_region
        },
        {
          name  = "ENVIRONMENT"
          value = var.common.environment
        },
        {
          name  = "SERVICE_NAME"
          value = var.common.service_name
        },
        {
          name  = "LOGS_GROUP"
          value = local.log_groups.logs_group
        },
        {
          name  = "LOG_RETENTION"
          value = tostring(var.environment_config.log_retention)
        },
        {
          name  = "IMAGE_TAG"
          value = var.gw_api_image_tag
        },
        {
          name  = "AOT_CONFIG_CONTENT"
          value = file(local.otel_collector_config)
        },
        {
          name  = "OBSERVABILITY_S3_BUCKET"
          value = var.s3_bucket_name
        },
        {
          name  = "APP_HASH"
          value = local.app_hash
        }
      ]
      healthCheck = {
        command     = ["CMD", "/healthcheck"]
        interval    = 30
        timeout     = 5
        retries     = 3
        startPeriod = 30
      }
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.otel_collector_logs.name
          "awslogs-region"        = var.common.aws_region
          "awslogs-stream-prefix" = "otel-collector"
        }
      }
      # Container insights specific configurations
      # dockerLabels = {
      #   "com.amazonaws.ecs.container-insights" = "enabled"
      # }
    }
  ])
  tags = var.common_tags
}
