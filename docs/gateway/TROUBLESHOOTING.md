# Troubleshooting

Common issues and solutions organized by symptom.

## Deployment Issues

### Terraform errors

**Symptom:** `terraform apply` fails

**Check:**

```bash
cd infrastructure
terraform validate
terraform plan -var-file=dev.local.tfvars
```

**Common causes:**

- Missing required variables in tfvars file
- Invalid AWS credentials
- Resource name conflicts
- Backend not initialized

**Solution:**

```bash
# Reinitialize backend
terraform init --backend-config=backend/dev.tfbackend

# Verify credentials
aws sts get-caller-identity

# Check for conflicts
terraform state list
```

### ECS tasks not starting

**Symptom:** ECS service shows 0 running tasks

**Check logs:**

```bash
aws logs tail /aws/ecs/bedrock-gateway-dev --follow
```

**Common causes:**

- Container image pull failures
- Invalid environment variables
- Insufficient IAM permissions
- Health check failures

**Solution:**

- Verify ECR image exists and is accessible
- Check ECS task definition environment variables
- Review IAM task role permissions
- Adjust health check grace period

### Health check failures

**Symptom:** ALB target health checks failing

**Check:**

```bash
# Test health endpoint directly
curl https://<alb-dns>/health

# Check ECS task logs
aws logs tail /aws/ecs/bedrock-gateway-dev --follow --filter-pattern "ERROR"
```

**Common causes:**

- Application not listening on correct port
- Security group blocking traffic
- Valkey connection failures
- Application startup errors

**Solution:**

- Verify container port 8000 is exposed
- Check security group rules allow ALB → ECS traffic
- Verify Valkey endpoint is accessible
- Review application startup logs

## Authentication Issues

### Token validation failures

**Symptom:** 401 Unauthorized responses

**Check token:**

```bash
echo $TOKEN | cut -d. -f2 | base64 -d | jq
```

**Common causes:**

- Token expired
- Invalid signature (JWKS mismatch)
- Wrong issuer
- Wrong audience
- Missing required scopes

**Solution:**

- Get fresh token from OAuth provider
- Verify `OAUTH_JWKS_URL` matches provider
- Verify `OAUTH_ISSUER` matches token `iss` claim
- Verify `JWT_AUDIENCE` matches token `aud` claim
- Verify token has required scopes in `JWT_ALLOWED_SCOPES`

### OAuth provider errors

**Symptom:** Cannot get OAuth token

**Check:**

```bash
curl -v -X POST <token_url> \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=client_credentials" \
  -d "client_id=<client_id>" \
  -d "client_secret=<client_secret>"
```

**Common causes:**

- Invalid client credentials
- Wrong token URL
- Client not configured for client credentials flow
- Missing audience parameter

**Solution:**

- Verify client_id and client_secret in OAuth provider
- Check token URL (usually `https://<provider>/oauth/token`)
- Enable client credentials grant in OAuth provider
- Add audience parameter if required by provider

### JWT claim issues

**Symptom:** Token validates but requests fail

**Check claims:**

```bash
echo $TOKEN | cut -d. -f2 | base64 -d | jq
```

**Required claims:**

- `iss` (issuer) - must match `OAUTH_ISSUER`
- `aud` (audience) - must match `JWT_AUDIENCE`
- `exp` (expiration) - must be in future
- `client_id` or `sub` or `azp` - used for rate limiting

**Solution:**

- Configure OAuth provider to include required claims
- Update gateway environment variables to match provider
- Ensure token includes client identifier claim

## Rate Limiting Issues

### Unexpected 429 errors

**Symptom:** Rate limit exceeded but usage seems low

**Check rate limit headers:**

```bash
curl -i https://<alb-dns>/model/<model-id>/converse \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": [{"text": "Hi"}]}]}'
```

**Headers:**

- `X-RateLimit-Limit` - Total quota
- `X-RateLimit-Remaining` - Remaining quota
- `X-RateLimit-Reset` - Reset timestamp

**Common causes:**

- Client quota too low
- Account quota exhausted
- Multiple clients sharing same client_id
- Token estimation inaccurate

**Solution:**

- Increase client quota in YAML config
- Add more AWS accounts
- Use unique client_id per application
- Monitor actual token usage

### Rate limits not working

**Symptom:** No rate limiting applied

**Check:**

```bash
# Verify rate limiting enabled
aws ecs describe-task-definition \
  --task-definition bedrock-gateway-dev \
  --query 'taskDefinition.containerDefinitions[0].environment[?name==`RATE_LIMITING_ENABLED`]'

# Check Valkey connectivity
aws elasticache describe-cache-clusters \
  --cache-cluster-id bedrock-gateway-dev
```

**Common causes:**

- `RATE_LIMITING_ENABLED=false`
- Valkey connection failures
- YAML config not loaded
- Client not matched in config

**Solution:**

- Set `RATE_LIMITING_ENABLED=true` in Terraform
- Verify Valkey security group allows ECS access
- Check YAML file exists in container
- Add client to YAML config or use `default` client

### Valkey connection errors

**Symptom:** Logs show Valkey connection failures

**Check:**

```bash
# Get Valkey endpoint
aws elasticache describe-cache-clusters \
  --cache-cluster-id bedrock-gateway-dev \
  --show-cache-node-info

# Test connectivity from ECS task
aws ecs execute-command \
  --cluster bedrock-gateway-dev \
  --task <task-id> \
  --container gateway \
  --interactive \
  --command "/bin/sh"
```

**Common causes:**

- Security group not allowing ECS → Valkey traffic
- Wrong Valkey endpoint
- Valkey cluster not available
- Network connectivity issues

**Solution:**

- Add ECS security group to Valkey ingress rules
- Verify `VALKEY_URL` environment variable
- Check Valkey cluster status
- Verify VPC networking configuration

## Request Issues

### 403 Forbidden from Bedrock

**Symptom:** Gateway returns 403 from Bedrock API

**Check IAM role:**

```bash
# Verify role can be assumed
aws sts assume-role \
  --role-arn arn:aws:iam::<account-id>:role/BedrockGatewayRole \
  --role-session-name test

# Check role permissions
aws iam get-role-policy \
  --role-name BedrockGatewayRole \
  --policy-name BedrockAccess
```

**Common causes:**

- IAM role missing Bedrock permissions
- Trust relationship not configured
- Model not enabled in account
- VPC endpoint condition mismatch

**Solution:**

- Add `bedrock:InvokeModel` permission to role
- Configure trust relationship for web identity federation
- Enable model access in Bedrock console
- Update VPC endpoint condition in IAM policy

### High latency

**Symptom:** Requests taking >2 seconds

**Check metrics:**

```bash
aws cloudwatch get-metric-statistics \
  --namespace BedrockGateway \
  --metric-name RequestLatency \
  --start-time $(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 \
  --statistics Average,Maximum
```

**Common causes:**

- STS assume role latency (first request)
- Valkey connection latency
- ECS task CPU/memory throttling
- Bedrock API latency

**Solution:**

- Credential caching reduces subsequent requests
- Use Valkey in same AZ as ECS tasks
- Increase ECS task CPU/memory
- Check Bedrock service health

### Streaming failures

**Symptom:** Streaming responses fail or timeout

**Check:**

```bash
curl -N -X POST https://<alb-dns>/model/<model-id>/converse-stream \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": [{"text": "Hi"}]}]}'
```

**Common causes:**

- ALB idle timeout too short
- Client timeout too short
- Network interruption
- Bedrock streaming errors

**Solution:**

- Increase ALB idle timeout (default 60s)
- Increase client timeout
- Check network stability
- Review Bedrock streaming documentation

## Multi-Account Issues

### Account selection problems

**Symptom:** Requests always use same account

**Check logs:**

```bash
aws logs tail /aws/ecs/bedrock-gateway-dev --follow --filter-pattern "account_id"
```

**Common causes:**

- Only one account configured
- Other accounts at quota limit
- Client not assigned to multiple accounts
- Account limits not configured

**Solution:**

- Add multiple accounts to `shared_account_ids`
- Increase account quotas in YAML config
- Assign client to multiple accounts in YAML
- Configure account limits for all accounts

### IAM role assumption failures

**Symptom:** Cannot assume role in shared account

**Check:**

```bash
# Test assume role
aws sts assume-role-with-web-identity \
  --role-arn arn:aws:iam::<account-id>:role/BedrockGatewayRole \
  --role-session-name test \
  --web-identity-token $TOKEN
```

**Common causes:**

- Trust relationship not configured
- Role doesn't exist in shared account
- Token issuer not in trust policy
- VPC endpoint condition mismatch

**Solution:**

- Create role in shared account with Terraform
- Add OAuth issuer to trust relationship
- Update VPC endpoint condition if using private endpoints
- Verify role ARN format

## Network Issues

### VPC endpoint problems

**Symptom:** Cannot reach AWS services

**Check endpoints:**

```bash
aws ec2 describe-vpc-endpoints \
  --filters "Name=vpc-id,Values=<vpc-id>"
```

**Common causes:**

- VPC endpoint not created
- Security group blocking traffic
- Route table not updated
- DNS resolution failures

**Solution:**

- Create required VPC endpoints (Bedrock, STS, etc.)
- Add ECS security group to endpoint security groups
- Associate endpoint with private subnets
- Enable DNS resolution in VPC

### Security group issues

**Symptom:** Connection timeouts

**Check security groups:**

```bash
aws ec2 describe-security-groups \
  --filters "Name=tag:Name,Values=bedrock-gateway-*"
```

**Common causes:**

- ALB → ECS traffic blocked
- ECS → Valkey traffic blocked
- ECS → VPC endpoints blocked
- Egress rules too restrictive

**Solution:**

- Allow ALB security group → ECS security group on port 8000
- Allow ECS security group → Valkey security group on port 6379
- Allow ECS security group → VPC endpoint security groups on port 443
- Add egress rules for required destinations

### DNS resolution

**Symptom:** Cannot resolve hostnames

**Check:**

```bash
# From ECS task
nslookup <alb-dns>
nslookup bedrock-runtime.us-east-1.amazonaws.com
```

**Common causes:**

- VPC DNS resolution disabled
- Private hosted zone not associated
- VPC endpoint DNS not enabled

**Solution:**

- Enable DNS resolution in VPC settings
- Associate private hosted zones with VPC
- Enable private DNS for VPC endpoints

## Performance Issues

### High CPU usage

**Symptom:** ECS tasks at high CPU utilization

**Check:**

```bash
aws cloudwatch get-metric-statistics \
  --namespace AWS/ECS \
  --metric-name CPUUtilization \
  --dimensions Name=ServiceName,Value=bedrock-gateway-service \
  --start-time $(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 \
  --statistics Average,Maximum
```

**Solution:**

- Increase ECS task CPU allocation
- Enable auto-scaling
- Add more ECS tasks
- Review application performance

### High memory usage

**Symptom:** ECS tasks at high memory utilization

**Check:**

```bash
aws cloudwatch get-metric-statistics \
  --namespace AWS/ECS \
  --metric-name MemoryUtilization \
  --dimensions Name=ServiceName,Value=bedrock-gateway-service \
  --start-time $(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 \
  --statistics Average,Maximum
```

**Solution:**

- Increase ECS task memory allocation
- Review credential cache size
- Check for memory leaks in logs
- Enable auto-scaling

### Cache hit rate low

**Symptom:** High STS API costs or latency

**Check logs:**

```bash
aws logs tail /aws/ecs/bedrock-gateway-dev --follow --filter-pattern "cache"
```

**Solution:**

- Increase credential cache TTL (default 1 hour)
- Verify Valkey is accessible
- Check Valkey memory limits
- Monitor cache eviction rate

## Getting More Help

If issues persist:

1. **Check logs:** `aws logs tail /aws/ecs/bedrock-gateway-dev --follow`
2. **Enable debug logging:** Set `LOG_LEVEL=DEBUG` in environment variables
3. **Check X-Ray traces:** Review distributed traces in AWS X-Ray console
4. **Review metrics:** Check CloudWatch dashboard for anomalies

## Related Documentation

- [Deployment Guide](01-setup/02-deployment.md)
- [OAuth Configuration](01-setup/03-oauth.md)
- [Rate Limiting](01-setup/04-rate-limiting.md)
- [Operations Guide](03-architecture/04-operations.md)
