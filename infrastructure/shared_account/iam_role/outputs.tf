output "role_arn" {
  description = "ARN of the created IAM role"
  value       = aws_iam_role.oauth_federation_role.arn
}

output "role_name" {
  description = "Name of the created IAM role"
  value       = aws_iam_role.oauth_federation_role.name
}
