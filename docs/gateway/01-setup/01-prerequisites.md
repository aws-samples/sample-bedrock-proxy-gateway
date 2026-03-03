# Prerequisites

What you need before deploying the gateway.

## AWS account requirements

You need at least two AWS accounts:

- **Central account** - Hosts the gateway infrastructure (Application Load Balancer, Amazon Elastic Container Service, ElastiCache)
- **Shared accounts** - Provide access to Amazon Bedrock models (one or more accounts)

### Required AWS permissions

Your AWS user or role needs permissions to create:

- [Amazon Virtual Private Cloud (Amazon VPC)](https://aws.amazon.com/vpc/) resources (VPC, subnets, security groups, VPC endpoints)
- Application Load Balancer (ALB) resources
- [Amazon Elastic Container Service (Amazon ECS)](https://aws.amazon.com/ecs/) clusters and services
- [Amazon ElastiCache](https://aws.amazon.com/elasticache/) for Valkey clusters
- [AWS Identity and Access Management (IAM)](https://aws.amazon.com/iam/) roles and policies
- [Amazon Simple Storage Service (Amazon S3)](https://aws.amazon.com/s3/) buckets (for Terraform state)
- [Amazon DynamoDB](https://aws.amazon.com/dynamodb/) tables (for Terraform state locking)

### Amazon Bedrock access

Each shared account needs:

1. Amazon Bedrock enabled in your region
2. Model access granted for the models you want to use

To check available models:

```bash
aws bedrock list-foundation-models --region us-east-1
```

To request model access, visit the Amazon Bedrock console and choose **Model access** in the navigation pane.

## Tools and software

### AWS Command Line Interface (AWS CLI)

Install AWS CLI v2 and configure credentials:

```bash
# Install (macOS)
brew install awscli

# Install (Linux)
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
unzip awscliv2.zip
sudo ./aws/install

# Configure
aws configure
```

For more information, refer to [Installing or updating the latest version of the AWS CLI](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html).

### Terraform

Install Terraform 1.5 or later:

```bash
# macOS
brew install terraform

# Linux
wget https://releases.hashicorp.com/terraform/1.5.0/terraform_1.5.0_linux_amd64.zip
unzip terraform_1.5.0_linux_amd64.zip
sudo mv terraform /usr/local/bin/
```

Verify installation:

```bash
terraform version
```

For more information, refer to [Install Terraform](https://developer.hashicorp.com/terraform/tutorials/aws-get-started/install-cli).

### Docker (optional)

Docker is optional but useful for local development and testing.

```bash
# macOS
brew install docker

# Linux
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
```

For more information, refer to [Get Docker](https://docs.docker.com/get-docker/).

### Git

Git is required to clone the repository:

```bash
# macOS
brew install git

# Linux
sudo yum install git  # Amazon Linux
sudo apt install git  # Ubuntu
```

## OAuth 2.0 provider

The gateway requires an OAuth 2.0 provider for authentication. You have two options:

### Option 1: Use your existing enterprise provider (recommended)

If your organization already uses an identity provider, you can integrate with:

- **Okta** - Enterprise identity platform
- **Auth0** - Flexible authentication service
- **Azure Active Directory** - Microsoft's identity platform
- **Keycloak** - Open-source identity solution
- **Any OAuth 2.0 provider** that supports client credentials flow

You need:

- JWKS URL (usually `https://your-provider/.well-known/jwks.json`)
- Issuer URL
- Audience value
- Required scopes

### Option 2: Set up Auth0 for testing

If you don't have an enterprise OAuth provider, you can create a free Auth0 account for testing.

For instructions on setting up Auth0, refer to [OAuth Configuration](03-oauth.md).

## Network access

### Outbound internet access

The gateway needs outbound internet access to:

- Reach your OAuth provider's JWKS endpoint
- Access AWS services (if not using VPC endpoints)
- Pull container images from Amazon Elastic Container Registry (Amazon ECR)

### Inbound access

Choose your deployment model:

- **Public ALB** - Accessible from the internet (requires public subnets)
- **Internal ALB** - Accessible only from your VPC or connected networks

## Checklist

Before you start deployment, verify you have:

- [ ] Two or more AWS accounts
- [ ] AWS CLI v2 installed and configured
- [ ] Terraform 1.5+ installed
- [ ] IAM permissions to create infrastructure
- [ ] Amazon Bedrock access in shared accounts
- [ ] OAuth 2.0 provider (existing or Auth0 account)
- [ ] OAuth provider details (JWKS URL, issuer, audience, scopes)

## Next steps

After you complete the prerequisites, proceed to [Deployment](02-deployment.md) to deploy the gateway.
