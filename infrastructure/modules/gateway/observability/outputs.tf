# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

output "s3_bucket_name" {
  description = "Name of the observability S3 bucket"
  value       = aws_s3_bucket.observability.bucket
}

output "observability_policy_arn" {
  description = "ARN of the observability access policy"
  value       = aws_iam_policy.observability_access.arn
}

output "observability_kms_key_arn" {
  description = "ARN of KMS key used for S3 and CloudWatch Logs encryption"
  value       = aws_kms_key.observability.arn
}

output "bedrock_logs_group_arn" {
  description = "ARN of the central CloudWatch Log Group for Bedrock model invocations"
  value       = aws_cloudwatch_log_group.bedrock_logs.arn
}
