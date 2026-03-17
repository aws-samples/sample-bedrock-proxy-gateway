# Enterprise Bedrock Proxy Gateway

An open-source sample implementation of an enterprise gateway for [Amazon Bedrock](https://aws.amazon.com/bedrock/) that demonstrates OAuth 2.0 (Open Authorization 2.0) authentication, rate limiting, multi-account routing, and comprehensive observability patterns.

**Note:** This is a sample implementation provided for educational and demonstration purposes. You should review, test, and customize this code for your specific requirements before deploying to any environment.

## What does this provide?

This sample demonstrates how to build a secure gateway for Amazon Bedrock with:

- **OAuth 2.0 authentication** - Integrate with identity providers like Okta, Auth0, Amazon Cognito, or Microsoft Entra ID
- **Rate limiting** - Token-based quotas per client to control costs
- **Multi-account routing** - Load balance across multiple AWS accounts with automatic failover
- **Credential caching** - Sub-10ms response times with Valkey cache
- **Streaming support** - Real-time model responses
- **Observability** - CloudWatch metrics, X-Ray tracing, and structured logging

## Architecture

```
Client → ALB → ECS (Fargate) → Valkey → Amazon Bedrock
                ↓
         CloudWatch + X-Ray
```

The gateway runs on [Amazon ECS](https://aws.amazon.com/ecs/) with [AWS Fargate](https://aws.amazon.com/fargate/) and uses [Application Load Balancer](https://aws.amazon.com/elasticloadbalancing/application-load-balancer/) for traffic distribution.

## Quick start

```bash
# Clone repository
git clone https://github.com/aws-samples/sample-bedrock-proxy-gateway.git
cd sample-bedrock-proxy-gateway

# Configure for your environment
cd infrastructure
cp dev.tfvars dev.local.tfvars
# Edit dev.local.tfvars with your OAuth provider and AWS account details

# Deploy
cd ..
./scripts/deploy.sh dev --apply
```

**Prerequisites:** AWS account, Terraform 1.5+, AWS CLI v2, OAuth 2.0 provider

**Note:** The `.local.*` files (`.local.tfvars`, `.local.tfbackend`, `.local.yaml`) are gitignored for your personal configurations. The base files contain generic examples for the open-source repository.

For detailed instructions, see the [Quick Start Guide](docs/gateway/QUICKSTART.md).

## Documentation

Complete documentation is in the [docs/gateway/](docs/gateway/) directory:

- **[Quick Start](docs/gateway/QUICKSTART.md)** - Deploy in 15 minutes
- **[Setup Guide](docs/gateway/01-setup/)** - Prerequisites, deployment, configuration
- **[Usage Guide](docs/gateway/02-usage/)** - Authentication, API usage, code examples
- **[Architecture](docs/gateway/03-architecture/)** - Components, security, operations
- **[Troubleshooting](docs/gateway/TROUBLESHOOTING.md)** - Common issues and solutions

## Examples

Interactive Jupyter notebooks are available in the [examples/](examples/) directory:

- Getting started and fundamentals
- Embeddings and RAG (Retrieval-Augmented Generation)
- Image generation and guardrails
- Rate limiting and operations

## Resources

- [Documentation](docs/gateway/)
- [Amazon Bedrock User Guide](https://docs.aws.amazon.com/bedrock/latest/userguide/)
- [Amazon Bedrock API Reference](https://docs.aws.amazon.com/bedrock/latest/APIReference/)
- [OAuth 2.0 Specification](https://oauth.net/2/)

## Security

See [CONTRIBUTING](CONTRIBUTING.md#security-issue-notifications) for more information.

## License

This library is licensed under the Apache 2.0 License. See the LICENSE file.

## Authors

[Yuvaraj Kesavan](https://github.com/YuvarajKesavan)
Rumeshkrishnan Mohan
[Nicola D'Orazio](https://github.com/Njk00)
[Konstantin Zerebcov](https://github.com/kzerebcov)
[David Sauerwein](https://github.com/Antropath)

Special thanks to [Olivier Brique](https://github.com/obriqaws) for his thorough review and suggestions that helped improve the solution.


