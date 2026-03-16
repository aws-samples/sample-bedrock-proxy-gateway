# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

# =============================================================================
# QUEUE DEPTH-BASED AUTOSCALING POLICY FOR PROACTIVE SCALING
# =============================================================================
# This policy uses application-level queue depth metrics to scale proactively
# before request queuing causes performance degradation. Based on performance
# test data showing gateway overhead increases significantly when queues build up.

resource "aws_appautoscaling_policy" "ecs_scale_queue_depth" {
  name               = "${local.ecs_service_name}-queue-depth-scaling"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.ecs_target.resource_id
  scalable_dimension = aws_appautoscaling_target.ecs_target.scalable_dimension
  service_namespace  = aws_appautoscaling_target.ecs_target.service_namespace

  target_tracking_scaling_policy_configuration {
    # Target: 8 active requests per task (based on performance test data)
    # PERFORMANCE TEST ANALYSIS:
    # - Queue buildup causes gateway overhead to jump from 170ms to 500-1000ms
    # - 429 errors start appearing when active requests exceed optimal capacity
    # - 8 active requests per task provides buffer before queue degradation
    # - Proactive scaling prevents the 170ms → 1000ms overhead spike observed in tests
    target_value = 8.0

    # Scale-out cooldown: 60 seconds
    # - Faster than request rate policy for proactive scaling
    # - Queue depth is more immediate indicator than request rate
    scale_out_cooldown = 60

    # Scale-in cooldown: 300 seconds (5 minutes)
    # - Conservative to prevent oscillation
    # - Queue depth can fluctuate more than request rate
    scale_in_cooldown = 300

    # Custom metric specification for active requests per task
    # Uses OTel metrics exported to CloudWatch by the collector
    customized_metric_specification {
      # Metric m1: Total active requests from application metrics
      # - OTel collector exports this from FastAPI application
      # - More accurate than ALB metrics for queue detection
      metrics {
        id          = "m1"
        return_data = false
        metric_stat {
          metric {
            namespace   = "${var.common.environment}/${var.common.service_name}" # Matches OTel collector namespace
            metric_name = "active_requests"
            dimensions {
              name  = "ServiceName"
              value = local.ecs_service_name
            }
            dimensions {
              name  = "Environment"
              value = var.common.environment
            }
          }
          stat = "Sum" # Total active requests across all tasks
        }
      }

      # Metric m2: Current number of running ECS tasks
      metrics {
        id          = "m2"
        return_data = false
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
          stat = "Average"
        }
      }

      # Metric m3: Active requests per task
      # - Directly measures application-level load
      # - Triggers scaling before ALB metrics show issues
      metrics {
        id          = "m3"
        expression  = "m1/m2"
        label       = "active_requests_per_task"
        return_data = true
      }
    }
  }

  depends_on = [aws_appautoscaling_target.ecs_target]
}
