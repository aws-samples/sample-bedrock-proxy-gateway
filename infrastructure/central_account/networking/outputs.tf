# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

output "vpc_id" {
  description = "ID of the created VPC"
  value       = aws_vpc.main.id
}

output "vpc_cidr_block" {
  description = "CIDR block of the VPC"
  value       = aws_vpc.main.cidr_block
}

output "private_subnet_ids" {
  description = "IDs of the private subnets"
  value       = aws_subnet.private[*].id
}

output "hosted_zone_id" {
  description = "ID of the Route53 hosted zone"
  value       = aws_route53_zone.main.zone_id
}

output "ecs_alb_target_group_arn" {
  description = "ARN of the ECS ALB target group"
  value       = aws_lb_target_group.ecs_target_group.arn
}

output "ecs_alb_listener_arn" {
  description = "ARN of the ECS ALB listener"
  value       = aws_lb_listener.ecs_listener_https.arn
}

output "ecs_alb_security_group_id" {
  description = "ID of the ECS ALB security group"
  value       = aws_security_group.ecs_alb_security_group.id
}

output "ecs_alb_dns_name" {
  description = "DNS name of the ECS ALB"
  value       = aws_lb.ecs_alb.dns_name
}

output "ecs_alb_arn" {
  description = "ARN of the ECS ALB"
  value       = aws_lb.ecs_alb.arn
}

output "bedrock_vpc_endpoint" {
  description = "Bedrock VPC Endpoint ID"
  value       = aws_vpc_endpoint.bedrock.id
}

output "bedrock_runtime_vpc_endpoint" {
  description = "Bedrock Runtime VPC Endpoint ID"
  value       = aws_vpc_endpoint.bedrock_runtime.id
}

output "bedrock_runtime_vpc_endpoint_dns" {
  description = "Bedrock Runtime VPC Endpoint DNS"
  value       = length(aws_vpc_endpoint.bedrock_runtime.dns_entry) > 0 ? lookup(aws_vpc_endpoint.bedrock_runtime.dns_entry[0], "dns_name", "") : ""
}

output "sts_vpc_endpoint_id" {
  description = "STS VPC Endpoint ID"
  value       = aws_vpc_endpoint.sts.id
}

output "sts_vpc_endpoint_dns" {
  description = "STS VPC Endpoint DNS"
  value       = length(aws_vpc_endpoint.sts.dns_entry) > 0 ? lookup(aws_vpc_endpoint.sts.dns_entry[0], "dns_name", "") : ""
}
