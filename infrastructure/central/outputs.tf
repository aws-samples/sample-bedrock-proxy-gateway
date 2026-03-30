# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

output "ecs_alb_dns_name" {
  value = module.central_account.ecs_alb_dns_name
}

output "ecs_cluster_name" {
  value = module.central_account.ecs_cluster_name
}

output "valkey_endpoint" {
  value = module.central_account.valkey_endpoint
}

output "bedrock_vpc_endpoint" {
  value = module.central_account.bedrock_vpc_endpoint
}

output "bedrock_runtime_vpc_endpoint" {
  value = module.central_account.bedrock_runtime_vpc_endpoint
}
