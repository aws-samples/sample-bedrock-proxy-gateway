# Advanced configuration

Advanced configuration options for enhanced security and customization.

This guide covers advanced configuration options including mTLS, custom domains, and VPC endpoint customization.

## Mutual TLS (mTLS)

Configure mutual TLS to require client certificates for enhanced security.

### How mTLS works

With mTLS enabled:

1. Client presents a certificate during TLS handshake
2. ALB validates the certificate against your CA bundle
3. ALB forwards the request only if the certificate is valid
4. Gateway processes the request normally

This adds certificate-based authentication on top of OAuth.

### Configure mTLS

Upload your CA certificate bundle to Amazon S3:

```bash
aws s3 cp ca-bundle.pem s3://your-bucket/certificates/ca-bundle.pem
```

Add to your Terraform variables:

```hcl
# infrastructure/dev.local.tfvars
mtls_cert_ca_s3_path = "s3://your-bucket/certificates/ca-bundle.pem"
```

Deploy:

```bash
./scripts/deploy.sh dev --apply
```

### Test mTLS

Test with a valid client certificate:

```bash
curl --cert client.crt --key client.key \
  https://<gateway-url>/health
```

Without a certificate, requests are rejected:

```bash
curl https://<gateway-url>/health
# Returns: SSL certificate problem
```

### Certificate requirements

Your client certificates must:

- Be signed by a CA in your CA bundle
- Not be expired
- Have valid subject and issuer fields
- Use supported key algorithms (RSA, ECDSA)

## Custom domains

Use a custom domain instead of the ALB DNS name.

### Create a certificate

Request a certificate in AWS Certificate Manager:

```bash
aws acm request-certificate \
  --domain-name gateway.example.com \
  --validation-method DNS \
  --region us-east-1
```

Validate the certificate by adding the DNS records shown in the ACM console.

### Configure custom domain

Add to your Terraform variables:

```hcl
# infrastructure/dev.local.tfvars
alb_certificate_arn = "arn:aws:acm:us-east-1:123456789012:certificate/abc123..."
custom_domain_name = "gateway.example.com"
```

Deploy:

```bash
./scripts/deploy.sh dev --apply
```

### Create DNS record

Create a CNAME record pointing to your ALB:

```bash
# Get ALB DNS name
ALB_DNS=$(cd infrastructure && terraform output -raw alb_dns_name)

# Create Route 53 record
aws route53 change-resource-record-sets \
  --hosted-zone-id Z1234567890ABC \
  --change-batch '{
    "Changes": [{
      "Action": "CREATE",
      "ResourceRecordSet": {
        "Name": "gateway.example.com",
        "Type": "CNAME",
        "TTL": 300,
        "ResourceRecords": [{"Value": "'$ALB_DNS'"}]
      }
    }]
  }'
```

Test your custom domain:

```bash
curl https://gateway.example.com/health
```

## Private ALB

Deploy an internal ALB accessible only from your VPC or connected networks.

### Configure private ALB

Add to your Terraform variables:

```hcl
# infrastructure/dev.local.tfvars
alb_internal = true
```

Deploy:

```bash
./scripts/deploy.sh dev --apply
```

The ALB is now only accessible from:

- Resources in the same VPC
- VPCs connected via VPC peering or Transit Gateway
- On-premises networks connected via VPN or Direct Connect

### Access from other VPCs

To access from another VPC, set up VPC peering:

```bash
# Create peering connection
aws ec2 create-vpc-peering-connection \
  --vpc-id vpc-gateway \
  --peer-vpc-id vpc-client \
  --peer-region us-east-1

# Accept peering connection
aws ec2 accept-vpc-peering-connection \
  --vpc-peering-connection-id pcx-xxx

# Update route tables in both VPCs
```

## VPC endpoint customization

Customize VPC endpoints for AWS services.

### Private DNS

Enable private DNS for VPC endpoints to use standard AWS service endpoints:

```hcl
# infrastructure/dev.local.tfvars
vpc_endpoint_private_dns_enabled = true
```

With private DNS enabled, you can use standard endpoints:

```python
# Uses VPC endpoint automatically
bedrock = boto3.client('bedrock-runtime', region_name='us-east-1')
```

Without private DNS, you must specify the VPC endpoint DNS:

```python
bedrock = boto3.client(
    'bedrock-runtime',
    endpoint_url='https://vpce-xxx.bedrock-runtime.us-east-1.vpce.amazonaws.com'
)
```

### Additional VPC endpoints

Add VPC endpoints for other AWS services:

```hcl
# infrastructure/dev.local.tfvars
additional_vpc_endpoints = [
  "secretsmanager",
  "kms",
  "ssm"
]
```

This creates VPC endpoints for:

- AWS Secrets Manager
- AWS Key Management Service
- AWS Systems Manager

## WAF rules

Customize AWS WAF rules for additional protection.

### Rate limiting at network layer

Add WAF rate limiting:

```hcl
# infrastructure/dev.local.tfvars
waf_rate_limit = 2000  # requests per 5 minutes per IP
```

This blocks IPs that exceed the rate limit, providing protection before requests reach the application.

### IP allowlist

Restrict access to specific IP ranges:

```hcl
# infrastructure/dev.local.tfvars
waf_ip_allowlist = [
  "203.0.113.0/24",
  "198.51.100.0/24"
]
```

Only requests from these IP ranges are allowed.

### Geo-blocking

Block requests from specific countries:

```hcl
# infrastructure/dev.local.tfvars
waf_geo_block_countries = ["CN", "RU", "KP"]
```

Uses ISO 3166-1 alpha-2 country codes.

## CloudWatch log retention

Configure log retention periods:

```hcl
# infrastructure/dev.local.tfvars
cloudwatch_log_retention_days = 30
```

Options: 1, 3, 5, 7, 14, 30, 60, 90, 120, 150, 180, 365, 400, 545, 731, 1827, 3653

Shorter retention reduces costs. Longer retention helps with compliance and troubleshooting.

## X-Ray tracing

Configure X-Ray sampling:

```hcl
# infrastructure/dev.local.tfvars
xray_sampling_rate = 0.1  # Sample 10% of requests
```

Lower sampling rates reduce costs while still providing visibility into performance issues.

## Auto-scaling

Customize ECS auto-scaling policies:

```hcl
# infrastructure/dev.local.tfvars
ecs_autoscaling_min_capacity = 2
ecs_autoscaling_max_capacity = 20
ecs_autoscaling_target_cpu = 70
ecs_autoscaling_target_memory = 80
```

The gateway scales based on:

- CPU utilization
- Memory utilization
- Request count
- ALB target response time

## Secrets Manager integration

Store sensitive configuration in Secrets Manager:

```bash
# Create secret
aws secretsmanager create-secret \
  --name bedrock-proxy-gateway/dev/config \
  --secret-string '{
    "oauth_client_secret": "xxx",
    "api_keys": ["key1", "key2"]
  }'
```

Reference in ECS task definition:

```hcl
secrets = [
  {
    name      = "OAUTH_CLIENT_SECRET"
    valueFrom = "arn:aws:secretsmanager:us-east-1:123456789012:secret:bedrock-proxy-gateway/dev/config:oauth_client_secret::"
  }
]
```

## Cost optimization

### Use Fargate Spot

For development and testing environments, use Fargate Spot for cost savings:

```hcl
# infrastructure/dev.tfvars
ecs_capacity_provider_strategy = [
  {
    capacity_provider = "FARGATE_SPOT"
    weight           = 100
    base             = 0
  }
]
```

Spot instances can be interrupted but cost ~70% less than regular Fargate.

### Right-size tasks

Adjust task CPU and memory based on actual usage:

```bash
# Check current utilization
aws cloudwatch get-metric-statistics \
  --namespace AWS/ECS \
  --metric-name CPUUtilization \
  --dimensions Name=ServiceName,Value=bedrock-proxy-gateway-service \
  --start-time $(date -u -d '7 days ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 3600 \
  --statistics Average,Maximum
```

If average CPU is consistently below 50%, you can reduce task size:

```hcl
# infrastructure/dev.local.tfvars
ecs_task_cpu = "512"     # Down from 1024
ecs_task_memory = "1024"  # Down from 2048
```

## Advanced security monitoring

Enhance security posture with runtime threat detection and monitoring.

### GuardDuty for ECS runtime monitoring

AWS GuardDuty provides threat detection for your ECS tasks, monitoring for suspicious behavior and potential security issues.

#### Enable GuardDuty ECS runtime monitoring

Enable GuardDuty in your AWS account:

```bash
# Enable GuardDuty
aws guardduty create-detector --enable

# Enable ECS runtime monitoring
DETECTOR_ID=$(aws guardduty list-detectors --query 'DetectorIds[0]' --output text)

aws guardduty update-detector \
  --detector-id $DETECTOR_ID \
  --features '[
    {
      "Name": "ECS_FARGATE_AGENT_MANAGEMENT",
      "Status": "ENABLED"
    }
  ]'
```

#### Configure GuardDuty findings alerts

Set up SNS notifications for GuardDuty findings:

```bash
# Create SNS topic for security alerts
aws sns create-topic --name bedrock-proxy-gateway-security-alerts

# Subscribe your security team
aws sns subscribe \
  --topic-arn arn:aws:sns:us-east-1:123456789012:bedrock-proxy-gateway-security-alerts \
  --protocol email \
  --notification-endpoint security-team@example.com

# Create EventBridge rule for GuardDuty findings
aws events put-rule \
  --name guardduty-ecs-findings \
  --event-pattern '{
    "source": ["aws.guardduty"],
    "detail-type": ["GuardDuty Finding"],
    "detail": {
      "resource": {
        "resourceType": ["ECSCluster"]
      }
    }
  }'

# Add SNS as target
aws events put-targets \
  --rule guardduty-ecs-findings \
  --targets "Id"="1","Arn"="arn:aws:sns:us-east-1:123456789012:bedrock-proxy-gateway-security-alerts"
```

#### Monitor for specific threats

GuardDuty detects threats including:

- **Cryptocurrency mining**: Unauthorized mining activity in ECS tasks
- **Malware**: Malicious software execution attempts
- **Backdoor communication**: Suspicious outbound connections
- **Privilege escalation**: Attempts to gain elevated permissions
- **Data exfiltration**: Unusual data transfer patterns

#### Respond to GuardDuty findings

When GuardDuty detects a threat:

1. Review the finding in the GuardDuty console
2. Investigate the affected ECS task
3. Check CloudWatch logs for suspicious activity
4. Isolate the task if necessary
5. Update security groups or network ACLs to block malicious IPs
6. Review and update IAM policies if privilege escalation is detected

Example automated response using Lambda:

```python
# Lambda function to automatically stop compromised tasks
import boto3

ecs = boto3.client('ecs')

def lambda_handler(event, context):
    finding = event['detail']

    if finding['severity'] >= 7:  # High or Critical
        # Extract ECS task ARN from finding
        task_arn = finding['resource']['ecsClusterDetails']['taskArn']
        cluster = finding['resource']['ecsClusterDetails']['clusterArn']

        # Stop the compromised task
        ecs.stop_task(
            cluster=cluster,
            task=task_arn,
            reason='GuardDuty security finding'
        )
```

## Bedrock Guardrails governance

Configure content filtering and PII protection using Bedrock Guardrails profiles.

### Guardrail profiles overview

Guardrail profiles are defined as YAML files in `infrastructure/shared_account/bedrock_guardrails/profiles/`. The gateway includes two example profiles:

- `baseline-security.yaml`: Basic content filtering for general use cases
- `comment-analysis.yaml`: Tailored for user-generated content analysis

### Configure forbidden topics

Add topic-based filtering to prevent discussions of sensitive subjects:

```yaml
# infrastructure/shared_account/bedrock_guardrails/profiles/enterprise-compliance.yaml
content_filters:
  - type: "HATE"
    input_strength: "MEDIUM"
    output_strength: "MEDIUM"
  - type: "INSULTS"
    input_strength: "MEDIUM"
    output_strength: "MEDIUM"
  - type: "SEXUAL"
    input_strength: "HIGH"
    output_strength: "HIGH"
  - type: "VIOLENCE"
    input_strength: "MEDIUM"
    output_strength: "MEDIUM"
  - type: "MISCONDUCT"
    input_strength: "HIGH"
    output_strength: "HIGH"
  - type: "PROMPT_ATTACK"
    input_strength: "HIGH"
    output_strength: "NONE"

# Define forbidden topics
forbidden_topics:
  - name: "Financial Advice"
    definition: "Providing specific investment recommendations, stock tips, or personalized financial planning advice"
    examples:
      - "Should I invest in cryptocurrency?"
      - "What stocks should I buy?"
    type: "DENY"
  - name: "Medical Diagnosis"
    definition: "Providing medical diagnoses, treatment recommendations, or prescribing medications"
    examples:
      - "Do I have cancer based on these symptoms?"
      - "What medication should I take for this condition?"
    type: "DENY"
  - name: "Legal Advice"
    definition: "Providing specific legal counsel or recommendations for legal proceedings"
    examples:
      - "Should I sue my employer?"
      - "How do I file for bankruptcy?"
    type: "DENY"

contextual_grounding:
  relevance_threshold: 0.75

forbidden_words:
  managed_lists:
    - type: "PROFANITY"

messages:
  blocked_input: "Your request contains content that violates our usage policies. Please rephrase your question."
  blocked_output: "The response has been blocked as it may contain prohibited information or advice."
```

### Configure PII data handling

Add PII filters to protect sensitive personal information:

```yaml
# infrastructure/shared_account/bedrock_guardrails/profiles/pii-protection.yaml
content_filters:
  - type: "PROMPT_ATTACK"
    input_strength: "HIGH"
    output_strength: "NONE"

# PII entity redaction
pii_entities:
  - type: "NAME"
    action: "ANONYMIZE"  # or "BLOCK"
  - type: "EMAIL"
    action: "ANONYMIZE"
  - type: "PHONE"
    action: "ANONYMIZE"
  - type: "SSN"
    action: "BLOCK"
  - type: "CREDIT_DEBIT_CARD_NUMBER"
    action: "BLOCK"
  - type: "ADDRESS"
    action: "ANONYMIZE"
  - type: "DATE_OF_BIRTH"
    action: "ANONYMIZE"
  - type: "DRIVERS_LICENSE"
    action: "BLOCK"
  - type: "PASSPORT_NUMBER"
    action: "BLOCK"
  - type: "USERNAME"
    action: "ANONYMIZE"
  - type: "PASSWORD"
    action: "BLOCK"
  - type: "AWS_ACCESS_KEY"
    action: "BLOCK"
  - type: "AWS_SECRET_KEY"
    action: "BLOCK"

contextual_grounding:
  relevance_threshold: 0.7

messages:
  blocked_input: "Your input contains sensitive personal information that cannot be processed."
  blocked_output: "The response has been blocked to protect sensitive information."
```

### PII action types

- **ANONYMIZE**: Replaces PII with a placeholder (e.g., `[NAME_1]`, `[EMAIL_1]`)
- **BLOCK**: Blocks the entire request or response if PII is detected

### Deploy custom guardrail profiles

After creating a new profile:

1. Add the profile to the guardrails configuration:

```hcl
# infrastructure/shared_account/bedrock_guardrails/main.tf
locals {
  guardrail_profiles = {
    "baseline-security"      = "baseline-security.yaml"
    "comment-analysis"       = "comment-analysis.yaml"
    "enterprise-compliance"  = "enterprise-compliance.yaml"
    "pii-protection"        = "pii-protection.yaml"
  }
}
```

1. Deploy the updated configuration:

```bash
cd infrastructure
terraform apply -target=module.shared_account.module.bedrock_guardrails
```

1. Associate the guardrail with your use case in the rate limiting configuration:

```yaml
# backend/app/core/rate_limit/config/dev.yaml
permissions:
  customer-support:
    name: "Customer Support"
    accounts: ["123456789012"]
    guardrail_id: "pii-protection"  # Reference the guardrail profile
    models:
      anthropic.claude-3-sonnet-20240229-v1:0:
        rpm: 100
        tpm: 50000
```

### Test guardrail effectiveness

Test your guardrail configuration:

```bash
# Test PII blocking
curl -X POST https://gateway.example.com/model/anthropic.claude-3-sonnet/invoke \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [{
      "role": "user",
      "content": "My SSN is 123-45-6789 and I need help"
    }]
  }'

# Expected: Request blocked with PII detection message

# Test forbidden topic
curl -X POST https://gateway.example.com/model/anthropic.claude-3-sonnet/invoke \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [{
      "role": "user",
      "content": "Should I invest all my money in Bitcoin?"
    }]
  }'

# Expected: Request blocked with forbidden topic message
```

### Monitor guardrail metrics

Track guardrail effectiveness in CloudWatch:

```bash
# View blocked requests by guardrail
aws cloudwatch get-metric-statistics \
  --namespace BedrockGateway \
  --metric-name GuardrailBlocked \
  --dimensions Name=GuardrailId,Value=pii-protection \
  --start-time $(date -u -d '24 hours ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 3600 \
  --statistics Sum
```

## Next steps

After configuring advanced features:

- Monitor your deployment in [Operations](../03-architecture/04-operations.md)
<!-- Security implementation details in Overview -->
- Learn about the architecture in [Architecture Overview](../03-architecture/01-overview.md)
