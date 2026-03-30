# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

resource "aws_kms_key" "val_key_kms_key" {
  description             = "Key to encrypt the valkey cache"
  enable_key_rotation     = true
  is_enabled              = true
  deletion_window_in_days = 30

  policy = jsonencode({
    Version = "2012-10-17"
    Id      = "key-valkey-cache"
    Statement = [{
      Sid    = "Enable IAM User Permissions"
      Effect = "Allow"
      Principal = {
        AWS = "arn:aws:iam::${var.common.aws_account_id}:root"
      }
      Action   = "kms:*"
      Resource = "*"
      },
      {
        Sid    = "Allow administration of the key"
        Effect = "Allow"
        Principal = {
          Service = "elasticache.amazonaws.com"
        }
        Action = [
          "kms:CancelKeyDeletion",
          "kms:Create*",
          "kms:Decrypt*",
          "kms:Delete*",
          "kms:Describe*",
          "kms:Disable*",
          "kms:Enable*",
          "kms:Encrypt",
          "kms:GenerateDataKey*",
          "kms:Get*",
          "kms:List*",
          "kms:Put*",
          "kms:Revoke*",
          "kms:ScheduleKeyDeletion",
          "kms:Update*",
        ]
        Resource = "*"
      }
    ]
  })
}

resource "aws_kms_alias" "valkey_cache_key_alias" {
  name          = "alias/valkey-cache-${var.common.environment}-key"
  target_key_id = aws_kms_key.val_key_kms_key.id
}
