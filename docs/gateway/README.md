# Enterprise Bedrock Proxy Gateway Documentation

An open-source sample implementation of an enterprise gateway for Amazon Bedrock that demonstrates OAuth 2.0 authentication, rate limiting, multi-account routing, and comprehensive observability patterns.

## Choose your path

**Deploy now** → [QUICKSTART.md](QUICKSTART.md) (15 minutes)

**New to this gateway** → [Setup Guide](01-setup/01-prerequisites.md)

**Configure features** → [Setup Section](01-setup/)

**Use the API** → [Usage Guide](02-usage/01-authentication.md)

**Troubleshoot issues** → [TROUBLESHOOTING.md](TROUBLESHOOTING.md)

**Understand internals** → [Architecture](03-architecture/)

## Documentation Structure

### Setup

Everything you need to deploy and configure the gateway.

- [Prerequisites](01-setup/01-prerequisites.md) - What you need before starting
- [Deployment](01-setup/02-deployment.md) - Deploy infrastructure and make first request
- [OAuth Configuration](01-setup/03-oauth.md) - Set up authentication
- [Rate Limiting](01-setup/04-rate-limiting.md) - Configure quotas and limits
- [Multi-Account](01-setup/05-multi-account.md) - Load balance across AWS accounts
- [Environment Variables](01-setup/06-environment-variables.md) - Configuration reference
- [Advanced Configuration](01-setup/07-advanced.md) - mTLS, custom domains, VPC endpoints

### Usage

How to use the gateway API.

- [Authentication](02-usage/01-authentication.md) - Get OAuth tokens
- [Making Requests](02-usage/02-making-requests.md) - API endpoints and examples
- [Code Examples](02-usage/03-code-examples.md) - Python code samples

### Architecture

Deep dive into how the gateway works.

- [Architecture Overview](03-architecture/) - System design and components
- [Overview](03-architecture/01-overview.md) - Components, design decisions, and security
- [Request Flow](03-architecture/02-request-flow.md) - How requests are processed
- [Networking](03-architecture/03-networking.md) - VPC, subnets, and endpoints
- [Operations](03-architecture/04-operations.md) - Monitoring, scaling, and maintenance
- [Development](03-architecture/05-development.md) - Local development and contributing

## What is This Gateway?

The Enterprise Bedrock Proxy Gateway provides secure, scalable access to Amazon Bedrock with:

- **OAuth 2.0 authentication** - Industry-standard authentication
- **Multi-account routing** - Load balance across AWS accounts
- **Rate limiting** - Control costs and prevent quota exhaustion
- **Credential caching** - Sub-10ms response times
- **Streaming support** - Real-time responses
- **Comprehensive observability** - CloudWatch metrics and X-Ray tracing

## Quick Links

**Deploy:**

- [Quick Start](QUICKSTART.md) - 15-minute deploy
- [Prerequisites](01-setup/01-prerequisites.md) - What you need
- [Deployment Guide](01-setup/02-deployment.md) - Full walkthrough

**Configure:**

- [OAuth Setup](01-setup/03-oauth.md) - Authentication
- [Rate Limits](01-setup/04-rate-limiting.md) - Quotas
- [Multi-Account](01-setup/05-multi-account.md) - Multiple AWS accounts

**Use:**

- [Authentication](02-usage/01-authentication.md) - Get tokens
- [Making Requests](02-usage/02-making-requests.md) - API guide
- [Code Examples](02-usage/03-code-examples.md) - Python samples

**Troubleshoot:**

- [Troubleshooting Guide](TROUBLESHOOTING.md) - Common issues and solutions

## Resources

- **Documentation:** This documentation site
- **Examples:** See [examples/](../../examples/) directory
