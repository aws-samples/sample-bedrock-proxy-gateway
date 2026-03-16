# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

resource "aws_kms_key" "logs_key" {
  description             = local.kms_key_description
  deletion_window_in_days = 7
  enable_key_rotation     = true
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "Enable IAM User Permissions"
        Effect = "Allow"
        Principal = {
          AWS = "arn:aws:iam::${var.common.aws_account_id}:root"
        }
        Action   = "kms:*"
        Resource = "*"
      },
      {
        Sid    = "Allow CloudWatch Logs"
        Effect = "Allow"
        Principal = {
          Service = "logs.amazonaws.com"
        }
        Action = [
          "kms:Encrypt",
          "kms:Decrypt",
          "kms:ReEncrypt*",
          "kms:GenerateDataKey*",
          "kms:DescribeKey"
        ]
        Resource = "*"
      }
    ]
  })
  tags = var.common_tags
}

resource "aws_kms_alias" "logs_key_alias" {
  name          = local.kms_alias_name
  target_key_id = aws_kms_key.logs_key.key_id
}

resource "aws_ecs_cluster" "api_cluster" {
  name = local.ecs_cluster_name

  # Enable Container Insights at cluster level
  setting {
    name  = "containerInsights"
    value = "enhanced"
  }

  tags = var.common_tags
}

resource "aws_cloudwatch_log_group" "ecs_logs" {
  name              = local.log_groups.ecs
  retention_in_days = 14
  kms_key_id        = aws_kms_key.logs_key.arn
  tags              = var.common_tags
}

resource "aws_cloudwatch_log_group" "otel_collector_logs" {
  name              = local.log_groups.otel_collector
  retention_in_days = 14
  kms_key_id        = aws_kms_key.logs_key.arn
  tags              = var.common_tags
}

resource "aws_cloudwatch_log_group" "api_otel_logs_group" {
  name              = local.log_groups.logs_group
  retention_in_days = 14
  kms_key_id        = aws_kms_key.logs_key.arn
  tags              = var.common_tags
}


resource "aws_security_group" "ecs_sg" {
  name        = local.security_group_name
  description = "Security group for ECS tasks"
  vpc_id      = var.vpc_id

  ingress {
    from_port       = 8000
    to_port         = 8000
    protocol        = "tcp"
    security_groups = [var.alb_security_group_id]
    description     = "Allow traffic from ALB"
  }

  egress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
    description = "Allow HTTPS outbound"
  }



  egress {
    from_port   = 6379
    to_port     = 6379
    protocol    = "tcp"
    cidr_blocks = [var.vpc_cidr_block]
    description = "Allow Valkey cache access"
  }
  tags = var.common_tags
}

resource "aws_ecs_service" "api_service" {
  name                   = local.ecs_service_name
  cluster                = aws_ecs_cluster.api_cluster.id
  task_definition        = aws_ecs_task_definition.api_task.arn
  desired_count          = var.environment_config.ecs_service_desired_count
  launch_type            = "FARGATE"
  platform_version       = "LATEST"
  enable_execute_command = true


  deployment_minimum_healthy_percent = 50
  deployment_maximum_percent         = 200

  # Enable service-level monitoring
  enable_ecs_managed_tags = true
  propagate_tags          = "SERVICE"

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  network_configuration {
    subnets          = var.private_subnet_ids
    security_groups  = [aws_security_group.ecs_sg.id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = var.alb_target_group_arn
    container_name   = local.api_container_name
    container_port   = 8000
  }

  health_check_grace_period_seconds = 120
  wait_for_steady_state             = true

}

resource "aws_appautoscaling_target" "ecs_target" {
  # Updated scaling limits for 8,000 req/min (133 req/s) target capacity
  # - Required: 133 req/s ÷ 5 req/s per task = 27 tasks minimum
  # - Buffer: 30 tasks for peak load handling
  # - Maximum: 40 tasks for extreme spikes (200 req/s capacity)
  max_capacity       = 40 # Supports up to 200 req/s (12,000 req/min)
  min_capacity       = var.environment_config.ecs_service_desired_count
  resource_id        = "service/${aws_ecs_cluster.api_cluster.name}/${aws_ecs_service.api_service.name}"
  scalable_dimension = "ecs:service:DesiredCount"
  service_namespace  = "ecs"

  depends_on = [aws_ecs_service.api_service]
}

# =============================================================================
# LEGACY CPU/MEMORY SCALING POLICIES (SAFETY NETS)
# =============================================================================
# These policies serve as safety nets in case the GenAI-specific policies
# miss edge cases. They use higher thresholds to avoid conflicts with
# the primary request-rate and response-time based scaling.

# CPU-based Target Tracking Scaling Policy (Safety Net)
resource "aws_appautoscaling_policy" "ecs_scale_cpu" {
  name               = "${local.ecs_service_name}-cpu-scaling-safety"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.ecs_target.resource_id
  scalable_dimension = aws_appautoscaling_target.ecs_target.scalable_dimension
  service_namespace  = aws_appautoscaling_target.ecs_target.service_namespace

  target_tracking_scaling_policy_configuration {
    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageCPUUtilization"
    }
    # Higher threshold (75%) to avoid conflicts with request-rate scaling
    # Only triggers if GenAI-specific policies miss something
    target_value       = 75.0
    scale_out_cooldown = 120 # Match other policies
    scale_in_cooldown  = 600 # Very conservative
  }

  depends_on = [aws_appautoscaling_target.ecs_target]
}

# Memory-based Target Tracking Scaling Policy (Safety Net)
resource "aws_appautoscaling_policy" "ecs_scale_memory" {
  name               = "${local.ecs_service_name}-memory-scaling-safety"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.ecs_target.resource_id
  scalable_dimension = aws_appautoscaling_target.ecs_target.scalable_dimension
  service_namespace  = aws_appautoscaling_target.ecs_target.service_namespace

  target_tracking_scaling_policy_configuration {
    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageMemoryUtilization"
    }
    # Higher threshold (90%) to avoid conflicts with request-rate scaling
    # Only triggers if GenAI-specific policies miss something
    target_value       = 90.0
    scale_out_cooldown = 120 # Match other policies
    scale_in_cooldown  = 600 # Very conservative
  }

  depends_on = [aws_appautoscaling_target.ecs_target]
}
