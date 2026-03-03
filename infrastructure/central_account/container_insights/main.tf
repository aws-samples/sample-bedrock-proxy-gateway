# Enable CloudWatch Container Insights for ECS at the account level
resource "aws_ecs_account_setting_default" "container_insights" {
  name  = "containerInsights"
  value = "enhanced"
}
