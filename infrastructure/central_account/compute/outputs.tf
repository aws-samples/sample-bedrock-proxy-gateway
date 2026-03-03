

output "ecs_cluster_name" {
  description = "Name of the ECS cluster"
  value       = aws_ecs_cluster.api_cluster.name
}

output "ecs_service_name" {
  description = "Name of the ECS service"
  value       = aws_ecs_service.api_service.name
}

output "restricted_role_session_name_suffix" {
  description = "IAM role trust policy within shared accounts enforces this suffix for all AssumeRoleWWI calls"
  value       = random_string.restricted_role_session_name_suffix.result
}
