# Quick Start (15 minutes)

Deploy the gateway and make your first request.

## Prerequisites

- AWS account with Amazon Bedrock access
- AWS CLI v2 configured
- Terraform 1.5+
- OAuth 2.0 provider (Auth0, Okta, Azure AD, or similar)

## Deploy

### 1. Setup backend

```bash
./scripts/setup.sh dev
```

### 2. Configure variables

Copy and edit the configuration file:

```bash
cd infrastructure
cp dev.tfvars dev.local.tfvars
# Edit dev.local.tfvars with your values
```

Example `dev.local.tfvars`:

```hcl
environment = "dev"

# OAuth (required)
oauth_jwks_url = "https://<tenant>.auth0.com/.well-known/jwks.json"
oauth_issuer = "https://<tenant>.auth0.com/"
jwt_audience = "bedrockproxygateway"
jwt_allowed_scopes = "bedrockproxygateway:invoke"

# AWS Accounts (comma-separated for multiple accounts)
shared_account_ids = "123456789012"  # Or "123456789012,234567890123" for multiple
central_account_id = "234567890123"
```

**Note:** `.local.tfvars` files are gitignored for your personal configurations.

### 3. Configure rate limits (optional)

For custom rate limits, copy and edit:

```bash
cd backend/app/core/rate_limit/config
cp base.yaml base.local.yaml
# Edit base.local.yaml with your values
```

```yaml
permissions:
  clients:
    default:
      quota:
        requests_per_minute: 100
        tokens_per_minute: 50000
      accounts:
        - "123456789012"

account_limits:
  "123456789012":
    us-east-1:
      anthropic.claude-3-5-sonnet-20241022-v2:0:
        input_tokens_per_minute: 400000
        output_tokens_per_minute: 80000
```

### 4. Deploy

```bash
./scripts/deploy.sh dev --apply
```

Deployment takes ~15-20 minutes. Note the `alb_dns_name` output.

### 5. Test

Get OAuth token:

```bash
TOKEN=$(curl -s -X POST <token_url> \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=client_credentials" \
  -d "client_id=<client_id>" \
  -d "client_secret=<client_secret>" \
  | jq -r '.access_token')
```

Test health:

```bash
curl https://<alb_dns_name>/health
```

Make first request:

```bash
curl -X POST https://<alb_dns_name>/model/anthropic.claude-3-5-sonnet-20241022-v2:0/converse \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {"role": "user", "content": [{"text": "Hello!"}]}
    ]
  }'
```

## Done

For detailed setup, see [Deployment Guide](01-setup/02-deployment.md).

For OAuth setup, see [OAuth Configuration](01-setup/03-oauth.md).

For troubleshooting, see [TROUBLESHOOTING.md](TROUBLESHOOTING.md).
