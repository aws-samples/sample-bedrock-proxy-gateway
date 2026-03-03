# =============================================================================
# REQUEST RATE-BASED AUTOSCALING POLICY FOR GENAI WORKLOADS
# =============================================================================
# This policy scales ECS tasks based on the average request rate per task,
# which is more suitable for GenAI workloads than CPU/memory-based scaling.
# GenAI requests have variable processing times and can queue up before
# resource limits are reached, making request rate a better scaling signal.

resource "aws_appautoscaling_policy" "ecs_scale_request_rate" {
  name               = "${local.ecs_service_name}-request-rate-scaling"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.ecs_target.resource_id
  scalable_dimension = aws_appautoscaling_target.ecs_target.scalable_dimension
  service_namespace  = aws_appautoscaling_target.ecs_target.service_namespace

  target_tracking_scaling_policy_configuration {
    # Target: 5 requests per second per task (based on performance test data)
    # PERFORMANCE TEST RESULTS (2025-09-15):
    # - Optimal: 16-20 req/s total (gateway overhead <200ms, no 429 errors)
    # - Degradation: 25+ req/s (overhead 400-500ms, 429 errors start)
    # - Hard limit: 30 req/s (overhead 700-1000ms, heavy 429 errors)
    # - With 4 tasks: 5 req/s/task = 20 req/s total (optimal performance)
    # - Scales before degradation point, maintains <200ms gateway overhead
    target_value = 5.0

    # Scale-out cooldown: 120 seconds
    # - Matches ECS task startup time (60s start period + 60s health checks)
    scale_out_cooldown = 120

    # Scale-in cooldown: 300 seconds (5 minutes)
    scale_in_cooldown = 300

    # Custom metric specification using CloudWatch metric math
    # Formula: Total ALB Requests ÷ (Running Tasks × 60 seconds) = Requests/Second/Task
    customized_metric_specification {
      # Metric m1: Total HTTP requests from ALB in the last minute
      metrics {
        id          = "m1"
        return_data = false # Intermediate metric, not returned in final result
        metric_stat {
          metric {
            namespace   = "AWS/ApplicationELB"
            metric_name = "RequestCount"
            dimensions {
              name  = "TargetGroup"
              value = var.alb_target_group_arn
            }
          }
          stat = "Sum" # Total requests in the time period
        }
      }

      # Metric m2: Current number of running ECS tasks
      # - Uses Container Insights which provides real-time task count
      metrics {
        id          = "m2"
        return_data = false # Intermediate metric, not returned in final result
        metric_stat {
          metric {
            namespace   = "ECS/ContainerInsights"
            metric_name = "RunningTaskCount"
            dimensions {
              name  = "ServiceName"
              value = local.ecs_service_name
            }
            dimensions {
              name  = "ClusterName"
              value = local.ecs_cluster_name
            }
          }
          stat = "Average" # Smooths out deployment-related fluctuations
        }
      }

      # Metric m3: Calculated requests per second per task
      # - Expression: m1/(m2*60) converts minute-based requests to per-second rate
      metrics {
        id          = "m3"
        expression  = "m1/(m2*60)" # Convert to requests per second per task
        label       = "request_rate_per_task"
        return_data = true # This is the metric used for scaling decisions
      }
    }
  }

  depends_on = [aws_appautoscaling_target.ecs_target]
}

# =============================================================================
# RESPONSE TIME-BASED AUTOSCALING POLICY FOR LATENCY MANAGEMENT
# =============================================================================
# This policy provides a secondary scaling trigger based on response time,
# ensuring user experience remains acceptable even when request rate scaling
# doesn't capture all performance issues (e.g., backend Bedrock API slowdowns).

resource "aws_appautoscaling_policy" "ecs_scale_response_time" {
  name               = "${local.ecs_service_name}-response-time-scaling"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.ecs_target.resource_id
  scalable_dimension = aws_appautoscaling_target.ecs_target.scalable_dimension
  service_namespace  = aws_appautoscaling_target.ecs_target.service_namespace

  target_tracking_scaling_policy_configuration {
    # Target: 3 seconds average response time (based on performance test data)
    # - Test shows gateway overhead increases significantly under load
    # - Normal: ~170ms overhead, Degraded: 500-1000ms overhead
    # - 3s threshold catches performance issues before severe degradation
    target_value = 3.0

    # Scale-out cooldown: 120 seconds
    scale_out_cooldown = 120

    # Scale-in cooldown: 600 seconds (10 minutes)
    scale_in_cooldown = 600

    # Single metric specification for ALB response time
    customized_metric_specification {
      # ALB Target Response Time metric
      # - Measures end-to-end response time from ALB perspective
      # - Includes network latency, application processing, and Bedrock API calls
      # - Average statistic smooths out individual request spikes
      # - More comprehensive than application-level metrics
      metrics {
        id          = "m1"
        return_data = true # Direct metric used for scaling decisions
        metric_stat {
          metric {
            namespace   = "AWS/ApplicationELB"
            metric_name = "TargetResponseTime"
            dimensions {
              name  = "TargetGroup"
              value = var.alb_target_group_arn
            }
          }
          stat = "Average" # Smooths out individual request variations
        }
      }
    }
  }

  depends_on = [aws_appautoscaling_target.ecs_target]
}
