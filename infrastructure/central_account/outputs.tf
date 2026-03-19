# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

output "ecs_alb_dns_name" {
  description = "DNS name of the ECS ALB"
  value       = module.networking.ecs_alb_dns_name
}

output "ecs_cluster_name" {
  description = "Name of the ECS cluster"
  value       = module.compute.ecs_cluster_name
}

output "ecs_service_name" {
  description = "Name of the ECS service"
  value       = module.compute.ecs_service_name
}

output "bedrock_vpc_endpoint" {
  description = "Bedrock VPC Endpoint"
  value       = module.networking.bedrock_vpc_endpoint
}

output "bedrock_runtime_vpc_endpoint" {
  description = "Bedrock Runtime VPC Endpoint"
  value       = module.networking.bedrock_runtime_vpc_endpoint
}

output "sts_vpc_endpoint_id" {
  description = "STS VPC Endpoint"
  value       = module.networking.sts_vpc_endpoint_id
}

output "observability_s3_bucket_name" {
  description = "Name of the observability S3 bucket"
  value       = module.observability.s3_bucket_name
}

output "observability_kms_key_arn" {
  description = "ARN of KMS key used for S3 and CloudWatch Logs encryption"
  value       = module.observability.observability_kms_key_arn
}

output "restricted_role_session_name_suffix" {
  value = module.compute.restricted_role_session_name_suffix
}

output "valkey_endpoint" {
  description = "Valkey cache endpoint"
  value       = module.caching.valkey_endpoint
}
