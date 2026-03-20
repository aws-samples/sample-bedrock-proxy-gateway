# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

resource "aws_iam_role" "ecs_execution_role" {
  name = local.ecs_execution_role_name
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ecs-tasks.amazonaws.com"
        }
      }
    ]
  })
  tags = var.common_tags
}

resource "aws_iam_role" "ecs_task_role" {
  name = local.ecs_task_role_name
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ecs-tasks.amazonaws.com"
        }
        Condition = {
          ArnLike = {
            "aws:SourceArn" = "arn:aws:ecs:${var.common.aws_region}:${var.common.aws_account_id}:task/*"
          }
          StringEquals = {
            "aws:SourceAccount" = var.common.aws_account_id
          }
        }
      }
    ]
  })
  tags = var.common_tags
}



resource "aws_iam_policy" "observability_policy" {
  name        = local.observability_policy_name
  description = "Policy for ECS observability (X-Ray, CloudWatch)"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = [
          "xray:PutTraceSegments",
          "xray:PutTelemetryRecords",
          "xray:GetSamplingRules",
          "xray:GetSamplingTargets",
          "xray:GetSamplingStatisticSummaries"
        ]
        Effect   = "Allow"
        Resource = "*"
        Condition = {
          StringEquals = {
            "aws:ResourceAccount" : var.common.aws_account_id
          }
        }
      },
      {
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents",
          "logs:DescribeLogStreams",
          "logs:DescribeLogGroups"
        ]
        Effect   = "Allow"
        Resource = "arn:aws:logs:${var.common.aws_region}:${var.common.aws_account_id}:*"
      },
      {
        Action = [
          "cloudwatch:PutMetricData",
          "cloudwatch:GetMetricStatistics",
          "cloudwatch:GetMetricData",
          "ecs:DescribeContainerInstances",
          "ecs:DescribeServices",
          "ecs:DescribeTasks",
          "ecs:ListTasks",
          "ec2:DescribeVolumes",
          "ec2:DescribeTags"
        ]
        Effect   = "Allow"
        Resource = "*"
        Condition = {
          StringEquals = {
            "aws:ResourceAccount" : var.common.aws_account_id
          }
        }
      },
      {
        Action = [
          "ssm:GetParameters",
          "ssm:GetParameter"
        ]
        Effect   = "Allow"
        Resource = "arn:aws:ssm:${var.common.aws_region}:${var.common.aws_account_id}:parameter/*"
      }
    ]
  })
  tags = var.common_tags
}

resource "aws_iam_role_policy_attachment" "ecs_execution_policy" {
  role       = aws_iam_role.ecs_execution_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# Add CloudWatch Container Insights policy to execution role
resource "aws_iam_role_policy_attachment" "ecs_execution_cloudwatch_policy" {
  role       = aws_iam_role.ecs_execution_role.name
  policy_arn = "arn:aws:iam::aws:policy/CloudWatchAgentServerPolicy"
}

resource "aws_iam_role_policy_attachment" "ecs_task_observability_policy" {
  role       = aws_iam_role.ecs_task_role.name
  policy_arn = aws_iam_policy.observability_policy.arn
}

resource "aws_iam_role_policy_attachment" "ecs_task_observability_access_policy" {
  role       = aws_iam_role.ecs_task_role.name
  policy_arn = var.observability_policy_arn
}

# ElastiCache policy for Valkey access
resource "aws_iam_policy" "elasticache_policy" {
  name        = "${local.ecs_task_role_name}-elasticache"
  description = "Policy for ECS task role to access ElastiCache Valkey"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = [
          "elasticache:DescribeServerlessCaches",
          "elasticache:Connect"
        ]
        Effect   = "Allow"
        Resource = "arn:aws:elasticache:${var.common.aws_region}:${var.common.aws_account_id}:serverlesscache:${local.valkey_cache_name}"
      }
    ]
  })
  tags = var.common_tags
}

resource "aws_iam_role_policy_attachment" "ecs_task_elasticache_policy" {
  role       = aws_iam_role.ecs_task_role.name
  policy_arn = aws_iam_policy.elasticache_policy.arn
}

# SSM policy for reading use case invocation config
resource "aws_iam_policy" "ssm_config_policy" {
  name        = "${local.ecs_execution_role_name}-ssm-config"
  description = "Policy for ECS execution role to read use case invocation config from SSM"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = [
          "kms:Decrypt"
        ]
        Effect   = "Allow"
        Resource = "arn:aws:kms:${var.common.aws_region}:${var.common.aws_account_id}:key/*"
      }
    ]
  })
  tags = var.common_tags
}

resource "aws_iam_role_policy_attachment" "ecs_execution_ssm_config_policy" {
  role       = aws_iam_role.ecs_execution_role.name
  policy_arn = aws_iam_policy.ssm_config_policy.arn
}
