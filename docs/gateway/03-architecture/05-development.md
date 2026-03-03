# Development

Local development and contributing.

## Local setup

### Prerequisites

- Python 3.12+
- Docker and Docker Compose
- AWS CLI v2
- Git

### Clone repository

```bash
git clone https://github.com/aws-samples/bedrock-proxy-gateway.git
cd bedrock-proxy-gateway
```

### Install dependencies

The project uses `uv` for Python dependency management:

```bash
# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install dependencies
uv sync

# Install pre-commit hooks
uv run pre-commit install
```

### Configure environment

Create `.env` file:

```bash
# .env
ENVIRONMENT=local
AWS_REGION=us-east-1
LOG_LEVEL=DEBUG
RATE_LIMITING_ENABLED=false
OTEL_SDK_DISABLED=true

# OAuth (use your test provider)
OAUTH_JWKS_URL=https://your-tenant.us.auth0.com/.well-known/jwks.json
OAUTH_ISSUER=https://your-tenant.us.auth0.com/
JWT_AUDIENCE=bedrockproxygateway

# AWS accounts
SHARED_ACCOUNT_IDS=123456789012
SHARED_ROLE_NAME=BedrockGatewayRole

# Local Valkey
VALKEY_URL=redis://localhost:6379
```

### Run locally

**With Docker Compose:**

```bash
docker compose up
```

This starts:

- Gateway application on port 8000
- Valkey on port 6379

**Without Docker:**

```bash
# Start Valkey
docker run -d -p 6379:6379 valkey/valkey:latest

# Run application
cd backend
uv run uvicorn app.main:app --reload --port 8000
```

### Test locally

```bash
# Health check
curl http://localhost:8000/health

# With OAuth token
curl -X POST http://localhost:8000/model/anthropic.claude-3-5-sonnet-20241022-v2:0/converse \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {"role": "user", "content": [{"text": "Hello"}]}
    ]
  }'
```

## Running tests

### Unit tests

```bash
# Run all unit tests
uv run pytest test/unit --cov=backend/app

# Run specific test file
uv run pytest test/unit/routes/test_bedrock_routes.py

# Run with coverage report
uv run pytest test/unit --cov=backend/app --cov-report=html
```

### Integration tests

```bash
# Run integration tests (requires AWS credentials)
uv run pytest test/integration

# Run specific integration test
uv run pytest test/integration/test_bedrock_integration.py
```

### Linting and formatting

```bash
# Run all checks
uv run pre-commit run --all-files

# Format code
uv run ruff format backend/

# Lint code
uv run ruff check backend/

# Type check
uv run mypy backend/
```

## Project structure

```
bedrock-proxy-gateway/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI application
│   │   ├── middleware/          # Auth, rate limiting, tracing
│   │   ├── routes/              # API endpoints
│   │   ├── services/            # Business logic
│   │   └── core/                # Core utilities
│   ├── Dockerfile
│   └── pyproject.toml
├── infrastructure/
│   ├── central_account/         # Central account resources
│   ├── shared_account/          # Shared account resources
│   └── workspaces/              # Environment configs
├── scripts/
│   ├── setup.sh                 # Backend setup
│   ├── deploy.sh                # Deploy script
│   └── destroy.sh               # Cleanup script
├── test/
│   ├── unit/                    # Unit tests
│   └── integration/             # Integration tests
└── docs/
    └── gateway/                 # Documentation
```

## Development workflow

### 1. Create branch

```bash
git checkout -b feature/my-feature
```

### 2. Make changes

Edit code, following project conventions:

- Use type hints
- Add docstrings
- Write tests
- Update documentation

### 3. Run tests

```bash
# Run tests
uv run pytest test/unit

# Check formatting
uv run pre-commit run --all-files
```

### 4. Commit changes

```bash
git add .
git commit -m "feat: add new feature"
```

Commit message format:

- `feat:` - New feature
- `fix:` - Bug fix
- `docs:` - Documentation
- `test:` - Tests
- `refactor:` - Code refactoring
- `chore:` - Maintenance

### 5. Push and create PR

```bash
git push origin feature/my-feature
```

Create pull request on GitHub.

## Code style

### Python

Follow PEP 8 with these tools:

- **ruff** - Linting and formatting
- **mypy** - Type checking
- **pre-commit** - Automated checks

### Formatting

```python
# Good
def process_request(
    client_id: str,
    model_id: str,
    messages: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """Process a Bedrock request.

    Args:
        client_id: Client identifier
        model_id: Bedrock model ID
        messages: Conversation messages

    Returns:
        Bedrock response
    """
    # Implementation
    pass
```

### Type hints

Always use type hints:

```python
from typing import Dict, List, Optional

def get_token(client_id: str) -> Optional[str]:
    """Get cached token for client."""
    return cache.get(client_id)
```

## Debugging

### Local debugging

Use Python debugger:

```python
import pdb; pdb.set_trace()
```

Or use IDE debugger (VS Code, PyCharm).

### ECS debugging

Use ECS Exec to access running container:

```bash
aws ecs execute-command \
  --cluster bedrock-gateway-dev \
  --task <task-id> \
  --container bedrock-gateway \
  --interactive \
  --command "/bin/bash"
```

### View logs

```bash
# Local
docker compose logs -f gateway

# ECS
aws logs tail /aws/ecs/bedrock-gateway-dev --follow
```

## Contributing

### Before contributing

1. Read the code of conduct
2. Check existing issues and PRs
3. Discuss major changes in an issue first

### Pull request process

1. Update documentation
2. Add tests for new features
3. Ensure all tests pass
4. Request review from maintainers

### Code review

Reviewers check for:

- Code quality and style
- Test coverage
- Documentation updates
- Security considerations
- Performance impact

## Troubleshooting

### Import errors

```bash
# Reinstall dependencies
uv sync --reinstall
```

### Test failures

```bash
# Run with verbose output
uv run pytest test/unit -v

# Run specific test
uv run pytest test/unit/test_auth.py::test_validate_token -v
```

### Docker issues

```bash
# Rebuild containers
docker compose build --no-cache

# Clean up
docker compose down -v
```

## Resources

- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Boto3 Documentation](https://boto3.amazonaws.com/v1/documentation/api/latest/index.html)
- [Terraform Documentation](https://www.terraform.io/docs)
- [AWS Bedrock Documentation](https://docs.aws.amazon.com/bedrock/)

## Next steps

- Review architecture in [Overview](01-overview.md)
- Understand request flow in [Request Flow](02-request-flow.md)
- Learn about security in [Overview](01-overview.md#security)
