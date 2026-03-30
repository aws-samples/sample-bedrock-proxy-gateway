# Operations

Monitoring, scaling, and maintenance.

## Monitoring

### Key metrics

**Health metrics:**

- ECS task count (running vs desired)
- ALB target health
- Valkey connection status
- Health check success rate

**Performance metrics:**

- Request latency (p50, p95, p99)
- Time-to-first-token (streaming)
- Credential cache hit rate
- Rate limit check latency

**Usage metrics:**

- Requests per minute
- Tokens per minute
- Rate limit rejections
- Error rate by type

**Cost metrics:**

- Bedrock API calls
- Token usage per client
- STS API calls
- Data transfer

### CloudWatch dashboards

Create dashboards for operational visibility:

```bash
# View ECS metrics
aws cloudwatch get-metric-statistics \
  --namespace AWS/ECS \
  --metric-name CPUUtilization \
  --dimensions Name=ServiceName,Value=bedrock-proxy-gateway-service \
  --start-time $(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 \
  --statistics Average,Maximum
```

### CloudWatch alarms

Set up alarms for critical issues:

**High error rate:**

```bash
aws cloudwatch put-metric-alarm \
  --alarm-name bedrock-proxy-gateway-high-errors \
  --metric-name 5XXError \
  --namespace AWS/ApplicationELB \
  --statistic Sum \
  --period 300 \
  --evaluation-periods 2 \
  --threshold 10 \
  --comparison-operator GreaterThanThreshold
```

**High CPU:**

```bash
aws cloudwatch put-metric-alarm \
  --alarm-name bedrock-proxy-gateway-high-cpu \
  --metric-name CPUUtilization \
  --namespace AWS/ECS \
  --statistic Average \
  --period 300 \
  --evaluation-periods 2 \
  --threshold 80 \
  --comparison-operator GreaterThanThreshold
```

### X-Ray tracing

Enable distributed tracing:

- End-to-end request flow
- Service dependencies
- Performance bottlenecks
- Error analysis

View traces in X-Ray console or query with AWS CLI.

### Logs

**Application logs:**

```bash
# Tail logs
aws logs tail /aws/ecs/bedrock-proxy-gateway-dev --follow

# Filter errors
aws logs tail /aws/ecs/bedrock-proxy-gateway-dev --follow --filter-pattern "ERROR"

# Search for specific client
aws logs tail /aws/ecs/bedrock-proxy-gateway-dev --follow --filter-pattern "client_id=xxx"
```

**ALB access logs:**

Stored in S3 bucket, analyze with Athena:

```sql
SELECT request_url, elb_status_code, COUNT(*) as count
FROM alb_logs
WHERE elb_status_code >= 400
GROUP BY request_url, elb_status_code
ORDER BY count DESC
LIMIT 10
```

## Scaling

### Auto-scaling policies

ECS service scales automatically based on:

**CPU utilization:**

- Target: 75%
- Scale out: Add tasks when CPU > 75%
- Scale in: Remove tasks when CPU < 75%

**Memory utilization:**

- Target: 90%
- Scale out: Add tasks when memory > 90%
- Scale in: Remove tasks when memory < 90%

**Request count:**

- Target: 1000 requests per task per minute
- Scale out: Add tasks when requests exceed target
- Scale in: Remove tasks when requests below target

**ALB queue depth:**

- Target: 0 queued requests
- Scale out: Add tasks when requests queue
- Scale in: Remove tasks when queue empty

### Manual scaling

Adjust desired task count:

```bash
aws ecs update-service \
  --cluster bedrock-proxy-gateway-dev \
  --service bedrock-proxy-gateway-service \
  --desired-count 10
```

### Capacity planning

**Calculate required capacity:**

1. Measure average request latency
2. Determine target requests per second
3. Calculate tasks needed: `(RPS * latency) / 1000`

Example:

- Target: 100 RPS
- Average latency: 2 seconds
- Tasks needed: (100 * 2) / 1000 = 0.2 tasks per request = 20 tasks

**Add buffer:**

- Production: 50% buffer (20 * 1.5 = 30 tasks)
- Development: 25% buffer

### Vertical scaling

Adjust task resources based on usage:

```hcl
# infrastructure/dev.local.tfvars
ecs_task_cpu = "2048"     # 2 vCPU
ecs_task_memory = "4096"  # 4 GB
```

Monitor CPU and memory utilization to right-size tasks.

## Maintenance

### Update application

Deploy new application version:

```bash
# Build and push image
cd backend
docker build -t bedrock-proxy-gateway:v2.0.0 .
docker push <ecr-repo>/bedrock-proxy-gateway:v2.0.0

# Update ECS service
aws ecs update-service \
  --cluster bedrock-proxy-gateway-dev \
  --service bedrock-proxy-gateway-service \
  --force-new-deployment
```

ECS performs rolling deployment with zero downtime.

### Update infrastructure

Deploy infrastructure changes:

```bash
# Update Terraform variables
vim infrastructure/dev.local.tfvars

# Apply changes
./scripts/deploy.sh dev --apply
```

Terraform applies only necessary changes.

### Update rate limits

Update rate limit configuration:

```bash
# Edit configuration
vim backend/app/core/rate_limit/config/dev.yaml

# Rebuild and deploy
docker build -t bedrock-proxy-gateway:latest .
docker push <ecr-repo>/bedrock-proxy-gateway:latest

# Force deployment
aws ecs update-service \
  --cluster bedrock-proxy-gateway-dev \
  --service bedrock-proxy-gateway-service \
  --force-new-deployment
```

### Rotate credentials

Rotate OAuth credentials:

```bash
# Update secret in Secrets Manager
aws secretsmanager update-secret \
  --secret-id bedrock-proxy-gateway/dev/oauth \
  --secret-string '{"client_id":"new-id","client_secret":"new-secret"}'

# Restart tasks to pick up new credentials
aws ecs update-service \
  --cluster bedrock-proxy-gateway-dev \
  --service bedrock-proxy-gateway-service \
  --force-new-deployment
```

### Backup and restore

**Terraform state:**

Stored in S3 with versioning enabled. Restore previous version if needed:

```bash
aws s3api list-object-versions \
  --bucket terraform-state-bucket \
  --prefix bedrock-proxy-gateway/

aws s3api get-object \
  --bucket terraform-state-bucket \
  --key bedrock-proxy-gateway/terraform.tfstate \
  --version-id <version-id> \
  terraform.tfstate
```

**Configuration:**

Store rate limit configurations in version control.

## Cost optimization

### Monitor costs

Track costs by service:

```bash
aws ce get-cost-and-usage \
  --time-period Start=2024-01-01,End=2024-01-31 \
  --granularity MONTHLY \
  --metrics BlendedCost \
  --group-by Type=SERVICE
```

### Optimize resources

**Right-size ECS tasks:**

- Monitor CPU/memory utilization
- Reduce task size if consistently low
- Increase if consistently high

**Use Fargate Spot:**

For development and testing:

```hcl
ecs_capacity_provider_strategy = [
  {
    capacity_provider = "FARGATE_SPOT"
    weight           = 100
  }
]
```

Saves ~70% on compute costs.

**Optimize VPC endpoints:**

- Use VPC endpoints to avoid NAT Gateway costs
- Remove unused VPC endpoints

**Adjust log retention:**

```hcl
cloudwatch_log_retention_days = 7  # Down from 14
```

### Track token usage

Monitor token usage per client:

```bash
aws logs tail /aws/ecs/bedrock-proxy-gateway-dev --follow --filter-pattern "usage"
```

Identify high-usage clients for cost allocation.

## Troubleshooting

### High error rate

**Check:**

1. CloudWatch logs for errors
2. Bedrock service health
3. Rate limit configuration
4. Recent deployments

**Common causes:**

- Bedrock quota exceeded
- Invalid rate limit configuration
- Application bugs
- Network issues

### High latency

**Check:**

1. ECS task CPU/memory
2. Valkey cache hit rate
3. STS assume role latency
4. Bedrock API latency

**Common causes:**

- Insufficient task resources
- Cold start (first request)
- Network latency
- Bedrock model latency

### Service unavailable

**Check:**

1. ECS task health
2. ALB target health
3. Security group rules
4. VPC connectivity

**Common causes:**

- All tasks unhealthy
- Health check failures
- Network misconfiguration
- Resource exhaustion

For detailed troubleshooting, refer to [TROUBLESHOOTING.md](../TROUBLESHOOTING.md).

## Next steps

- Review security implementation in [Overview](01-overview.md#security)
- Set up local development in [Development](05-development.md)
- Configure advanced features in [Advanced Configuration](../01-setup/07-advanced.md)
