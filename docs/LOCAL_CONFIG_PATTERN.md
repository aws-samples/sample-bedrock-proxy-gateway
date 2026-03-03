# Local Configuration Pattern

This project uses a `.local.*` file pattern to keep personal configurations separate from the repository's generic examples.

## Files That Support .local Pattern

### Terraform Configuration

- `infrastructure/dev.tfvars` → `infrastructure/dev.local.tfvars`
- `infrastructure/test.tfvars` → `infrastructure/test.local.tfvars`
- `infrastructure/backend-dev.tfbackend` → `infrastructure/backend-dev.local.tfbackend`
- `infrastructure/backend-test.tfbackend` → `infrastructure/backend-test.local.tfbackend`

### Rate Limit Configuration

- `backend/app/core/rate_limit/config/base.yaml` → `backend/app/core/rate_limit/config/base.local.yaml`
- `backend/app/core/rate_limit/config/dev.yaml` → `backend/app/core/rate_limit/config/dev.local.yaml`
- `backend/app/core/rate_limit/config/test.yaml` → `backend/app/core/rate_limit/config/test.local.yaml`

### Docker Compose

- `backend/app/docker-compose.yml` → `backend/app/docker-compose.override.yml`

## How It Works

1. **Base files** contain generic examples with placeholders (e.g., `123456789012`, `YOUR_OAUTH_CLIENT_ID`)
2. **Local files** contain your actual values (account IDs, client IDs, etc.)
3. **Scripts automatically prefer** `.local.*` files when they exist
4. **Git ignores** all `.local.*` files to keep your personal data private

## Usage

### First Time Setup

```bash
# Terraform variables
cd infrastructure
cp dev.tfvars dev.local.tfvars
# Edit dev.local.tfvars with your actual values

# Rate limit config (optional)
cd backend/app/core/rate_limit/config
cp base.yaml base.local.yaml
# Edit base.local.yaml with your actual account IDs and client IDs
```

### Deployment

Scripts automatically use `.local.*` files:

```bash
./scripts/deploy.sh dev --apply
# Uses dev.local.tfvars and backend-dev.local.tfbackend if they exist
```

## Benefits

1. **Clean repository** - Generic examples in version control
2. **Personal privacy** - Your actual IDs never committed
3. **Easy collaboration** - Contributors use their own `.local.*` files
4. **No conflicts** - Each developer has independent configurations
5. **Open source ready** - Repository contains no sensitive data

## Gitignore

All `.local.*` files are automatically ignored:

```gitignore
*.local.yaml
*.local.tfvars
*.local.tfbackend
docker-compose.override.yml
```
