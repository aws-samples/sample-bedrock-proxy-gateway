# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

# KMS Key for Bedrock CloudWatch Logs
resource "aws_kms_key" "bedrock_logs_key" {
  description             = "KMS key for Bedrock CloudWatch logs encryption"
  deletion_window_in_days = 7
  enable_key_rotation     = true

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          AWS = "arn:aws:iam::${var.aws_account_id}:root"
        }
        Action   = "kms:*"
        Resource = "*"
      },
      {
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

  tags = var.tags
}

resource "aws_kms_alias" "bedrock_logs_key_alias" {
  name          = var.kms_alias_name
  target_key_id = aws_kms_key.bedrock_logs_key.key_id
}

# CloudWatch Log Group for Bedrock
# Note: When shared and central accounts are the same, the log group is created
# in the central account module to avoid conflicts
resource "aws_cloudwatch_log_group" "bedrock_logs" {
  count             = var.aws_account_id != var.central_account_id ? 1 : 0
  name              = var.log_group_name
  retention_in_days = var.log_retention_days
  kms_key_id        = aws_kms_key.bedrock_logs_key.arn

  tags = var.tags
}
