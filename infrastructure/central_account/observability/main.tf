# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

# S3 bucket for observability data
resource "aws_s3_bucket" "observability" {
  #checkov:skip=CKV2_AWS_62: "Event notifications not required for observability data bucket"
  #checkov:skip=CKV_AWS_18: "Access logging not required for observability data bucket"
  #checkov:skip=CKV_AWS_144: "Cross-region replication not required for observability data bucket"
  #checkov:skip=CKV_AWS_21: "Versioning not required for observability logs bucket"
  bucket = local.s3_bucket_name
  tags   = var.common_tags
}

resource "aws_s3_bucket_server_side_encryption_configuration" "observability" {
  bucket = aws_s3_bucket.observability.id

  rule {
    apply_server_side_encryption_by_default {
      kms_master_key_id = aws_kms_key.observability.arn
      sse_algorithm     = "aws:kms"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "observability" {
  bucket = aws_s3_bucket.observability.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "observability" {
  bucket = aws_s3_bucket.observability.id

  rule {
    id     = "observability_data_lifecycle"
    status = "Enabled"

    filter {
      prefix = ""
    }

    expiration {
      days = var.common.environment == "dev" ? 180 : (var.common.environment == "test" ? 365 : 90)
    }

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }
}

# KMS key for encryption
resource "aws_kms_key" "observability" {
  description             = "KMS key for observability resources encryption"
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
        Sid    = "Allow S3 Service"
        Effect = "Allow"
        Principal = {
          Service = "s3.amazonaws.com"
        }
        Action = [
          "kms:Encrypt",
          "kms:Decrypt",
          "kms:ReEncrypt*",
          "kms:GenerateDataKey*",
          "kms:DescribeKey"
        ]
        Resource = "*"
      },
      {
        Sid    = "Allow Kinesis Service"
        Effect = "Allow"
        Principal = {
          Service = "kinesis.amazonaws.com"
        }
        Action = [
          "kms:Encrypt",
          "kms:Decrypt",
          "kms:ReEncrypt*",
          "kms:GenerateDataKey*",
          "kms:DescribeKey"
        ]
        Resource = "*"
      },
      {
        Sid    = "Allow SQS Service"
        Effect = "Allow"
        Principal = {
          Service = "sqs.amazonaws.com"
        }
        Action = [
          "kms:Encrypt",
          "kms:Decrypt",
          "kms:ReEncrypt*",
          "kms:GenerateDataKey*",
          "kms:DescribeKey"
        ]
        Resource = "*"
      },
      {
        Sid    = "Allow CloudWatch Logs"
        Effect = "Allow"
        Principal = {
          Service = "logs.${var.common.aws_region}.amazonaws.com"
        }
        Action = [
          "kms:Encrypt",
          "kms:Decrypt",
          "kms:ReEncrypt*",
          "kms:GenerateDataKey*",
          "kms:DescribeKey"
        ]
        Resource = "*"
        Condition = {
          ArnLike = {
            "kms:EncryptionContext:aws:logs:arn" = "arn:aws:logs:${var.common.aws_region}:${var.common.aws_account_id}:log-group:*"
          }
        }
      }
    ]
  })

  tags = var.common_tags
}

resource "aws_kms_alias" "observability" {
  name          = local.kms_alias_name
  target_key_id = aws_kms_key.observability.key_id
}

# Central CloudWatch Log Group for Bedrock model invocations
resource "aws_cloudwatch_log_group" "bedrock_logs" {
  name              = "/aws/bedrock/modelinvocations"
  retention_in_days = var.common.log_retention_days
  kms_key_id        = aws_kms_key.observability.arn

  tags = var.common_tags
}

# CloudWatch Logs resource policy for cross-account log sharing
resource "aws_cloudwatch_log_resource_policy" "cross_account_logs" {
  policy_name = "${local.resource_name}-cross-account-logs"

  policy_document = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowCrossAccountLogDelivery"
        Effect = "Allow"
        Principal = {
          Service = "bedrock.amazonaws.com"
        }
        Action = [
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "${aws_cloudwatch_log_group.bedrock_logs.arn}:*"
        Condition = {
          StringEquals = {
            "aws:SourceAccount" = split(",", var.shared_account_ids)
          }
        }
      }
    ]
  })
}
