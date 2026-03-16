# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

# =============================================================================
# VPC CREATION
# =============================================================================

resource "aws_vpc" "main" {
  #checkov:skip=CKV2_AWS_11: "VPC flow logging not required for dev/test environments"
  #checkov:skip=CKV2_AWS_12: "Default security group restrictions managed separately"
  cidr_block           = "10.0.0.0/16"
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = merge(
    var.common_tags,
    {
      Name = "${var.common.app_id}-${var.common.environment}-vpc"
    }
  )
}

# =============================================================================
# PRIVATE SUBNETS
# =============================================================================

data "aws_availability_zones" "available" {
  state = "available"
}

resource "aws_subnet" "private" {
  count             = 2
  vpc_id            = aws_vpc.main.id
  cidr_block        = "10.0.${count.index + 1}.0/24"
  availability_zone = data.aws_availability_zones.available.names[count.index]

  tags = merge(
    var.common_tags,
    {
      Name = "${var.common.app_id}-${var.common.environment}-private-${count.index + 1}"
    }
  )
}

# =============================================================================
# PUBLIC SUBNETS (for public ALB)
# =============================================================================

resource "aws_subnet" "public" {
  #checkov:skip=CKV_AWS_130: "Public subnets intentionally assign public IPs for public ALB"
  count                   = 2
  vpc_id                  = aws_vpc.main.id
  cidr_block              = "10.0.${count.index + 10}.0/24"
  availability_zone       = data.aws_availability_zones.available.names[count.index]
  map_public_ip_on_launch = true

  tags = merge(
    var.common_tags,
    {
      Name = "${var.common.app_id}-${var.common.environment}-public-${count.index + 1}"
    }
  )
}

# =============================================================================
# INTERNET GATEWAY
# =============================================================================

resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id

  tags = merge(
    var.common_tags,
    {
      Name = "${var.common.app_id}-${var.common.environment}-igw"
    }
  )
}

# =============================================================================
# NAT GATEWAY
# =============================================================================

resource "aws_eip" "nat" {
  domain = "vpc"

  tags = merge(
    var.common_tags,
    {
      Name = "${var.common.app_id}-${var.common.environment}-nat-eip"
    }
  )

  depends_on = [aws_internet_gateway.main]
}

resource "aws_nat_gateway" "main" {
  allocation_id = aws_eip.nat.id
  subnet_id     = aws_subnet.public[0].id

  tags = merge(
    var.common_tags,
    {
      Name = "${var.common.app_id}-${var.common.environment}-nat"
    }
  )

  depends_on = [aws_internet_gateway.main]
}

# =============================================================================
# VPC ENDPOINTS
# =============================================================================

resource "aws_vpc_endpoint" "bedrock" {
  vpc_id              = aws_vpc.main.id
  service_name        = "com.amazonaws.${var.common.aws_region}.bedrock"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = aws_subnet.private[*].id
  security_group_ids  = [aws_security_group.vpc_endpoints.id]
  private_dns_enabled = true

  tags = merge(
    var.common_tags,
    {
      Name = "${var.common.app_id}-${var.common.environment}-bedrock-endpoint"
    }
  )
}

resource "aws_vpc_endpoint" "bedrock_runtime" {
  vpc_id              = aws_vpc.main.id
  service_name        = "com.amazonaws.${var.common.aws_region}.bedrock-runtime"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = aws_subnet.private[*].id
  security_group_ids  = [aws_security_group.vpc_endpoints.id]
  private_dns_enabled = true

  tags = merge(
    var.common_tags,
    {
      Name = "${var.common.app_id}-${var.common.environment}-bedrock-runtime-endpoint"
    }
  )
}

resource "aws_vpc_endpoint" "sts" {
  vpc_id              = aws_vpc.main.id
  service_name        = "com.amazonaws.${var.common.aws_region}.sts"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = aws_subnet.private[*].id
  security_group_ids  = [aws_security_group.vpc_endpoints.id]
  private_dns_enabled = true

  tags = merge(
    var.common_tags,
    {
      Name = "${var.common.app_id}-${var.common.environment}-sts-endpoint"
    }
  )
}

resource "aws_vpc_endpoint" "elasticache" {
  vpc_id              = aws_vpc.main.id
  service_name        = "com.amazonaws.${var.common.aws_region}.elasticache"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = aws_subnet.private[*].id
  security_group_ids  = [aws_security_group.vpc_endpoints.id]
  private_dns_enabled = true

  tags = merge(
    var.common_tags,
    {
      Name = "${var.common.app_id}-${var.common.environment}-elasticache-endpoint"
    }
  )
}

# ECR API endpoint (for authentication)
resource "aws_vpc_endpoint" "ecr_api" {
  vpc_id              = aws_vpc.main.id
  service_name        = "com.amazonaws.${var.common.aws_region}.ecr.api"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = aws_subnet.private[*].id
  security_group_ids  = [aws_security_group.vpc_endpoints.id]
  private_dns_enabled = true

  tags = merge(
    var.common_tags,
    {
      Name = "${var.common.app_id}-${var.common.environment}-ecr-api-endpoint"
    }
  )
}

# ECR DKR endpoint (for pulling images)
resource "aws_vpc_endpoint" "ecr_dkr" {
  vpc_id              = aws_vpc.main.id
  service_name        = "com.amazonaws.${var.common.aws_region}.ecr.dkr"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = aws_subnet.private[*].id
  security_group_ids  = [aws_security_group.vpc_endpoints.id]
  private_dns_enabled = true

  tags = merge(
    var.common_tags,
    {
      Name = "${var.common.app_id}-${var.common.environment}-ecr-dkr-endpoint"
    }
  )
}

# S3 Gateway endpoint (for ECR to pull image layers from S3)
resource "aws_vpc_endpoint" "s3" {
  vpc_id            = aws_vpc.main.id
  service_name      = "com.amazonaws.${var.common.aws_region}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = [aws_vpc.main.default_route_table_id]

  tags = merge(
    var.common_tags,
    {
      Name = "${var.common.app_id}-${var.common.environment}-s3-endpoint"
    }
  )
}

# CloudWatch Logs endpoint (for ECS task logging)
resource "aws_vpc_endpoint" "logs" {
  vpc_id              = aws_vpc.main.id
  service_name        = "com.amazonaws.${var.common.aws_region}.logs"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = aws_subnet.private[*].id
  security_group_ids  = [aws_security_group.vpc_endpoints.id]
  private_dns_enabled = true

  tags = merge(
    var.common_tags,
    {
      Name = "${var.common.app_id}-${var.common.environment}-logs-endpoint"
    }
  )
}

# Secrets Manager endpoint (for OAuth M2M credentials)
resource "aws_vpc_endpoint" "secretsmanager" {
  vpc_id              = aws_vpc.main.id
  service_name        = "com.amazonaws.${var.common.aws_region}.secretsmanager"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = aws_subnet.private[*].id
  security_group_ids  = [aws_security_group.vpc_endpoints.id]
  private_dns_enabled = true

  tags = merge(
    var.common_tags,
    {
      Name = "${var.common.app_id}-${var.common.environment}-secretsmanager-endpoint"
    }
  )
}

# SSM endpoint (for guardrail configuration)
resource "aws_vpc_endpoint" "ssm" {
  vpc_id              = aws_vpc.main.id
  service_name        = "com.amazonaws.${var.common.aws_region}.ssm"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = aws_subnet.private[*].id
  security_group_ids  = [aws_security_group.vpc_endpoints.id]
  private_dns_enabled = true

  tags = merge(
    var.common_tags,
    {
      Name = "${var.common.app_id}-${var.common.environment}-ssm-endpoint"
    }
  )
}

# KMS endpoint (for decrypting secrets and parameters)
resource "aws_vpc_endpoint" "kms" {
  vpc_id              = aws_vpc.main.id
  service_name        = "com.amazonaws.${var.common.aws_region}.kms"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = aws_subnet.private[*].id
  security_group_ids  = [aws_security_group.vpc_endpoints.id]
  private_dns_enabled = true

  tags = merge(
    var.common_tags,
    {
      Name = "${var.common.app_id}-${var.common.environment}-kms-endpoint"
    }
  )
}

# X-Ray endpoint (for OTEL collector traces)
resource "aws_vpc_endpoint" "xray" {
  vpc_id              = aws_vpc.main.id
  service_name        = "com.amazonaws.${var.common.aws_region}.xray"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = aws_subnet.private[*].id
  security_group_ids  = [aws_security_group.vpc_endpoints.id]
  private_dns_enabled = true

  tags = merge(
    var.common_tags,
    {
      Name = "${var.common.app_id}-${var.common.environment}-xray-endpoint"
    }
  )
}

# =============================================================================
# SECURITY GROUP FOR VPC ENDPOINTS
# =============================================================================

resource "aws_security_group" "vpc_endpoints" {
  name        = "${var.common.app_id}-${var.common.environment}-vpc-endpoints"
  description = "Security group for VPC endpoints"
  vpc_id      = aws_vpc.main.id

  tags = merge(
    var.common_tags,
    {
      Name = "${var.common.app_id}-${var.common.environment}-vpc-endpoints-sg"
    }
  )
}

resource "aws_security_group_rule" "vpc_endpoints_ingress" {
  type              = "ingress"
  description       = "Allow HTTPS traffic from VPC CIDR"
  from_port         = 443
  to_port           = 443
  protocol          = "tcp"
  cidr_blocks       = [aws_vpc.main.cidr_block]
  security_group_id = aws_security_group.vpc_endpoints.id
}

resource "aws_security_group_rule" "vpc_endpoints_egress" {
  type              = "egress"
  description       = "Allow HTTPS traffic to VPC CIDR"
  from_port         = 443
  to_port           = 443
  protocol          = "tcp"
  cidr_blocks       = [aws_vpc.main.cidr_block]
  security_group_id = aws_security_group.vpc_endpoints.id
}

# =============================================================================
# ROUTE TABLES
# =============================================================================

# Public route table
resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main.id
  }

  tags = merge(
    var.common_tags,
    {
      Name = "${var.common.app_id}-${var.common.environment}-public-rt"
    }
  )
}

resource "aws_route_table_association" "public" {
  count          = 2
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

# Private route table
resource "aws_route_table" "private" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block     = "0.0.0.0/0"
    nat_gateway_id = aws_nat_gateway.main.id
  }

  tags = merge(
    var.common_tags,
    {
      Name = "${var.common.app_id}-${var.common.environment}-private-rt"
    }
  )
}

resource "aws_route_table_association" "private" {
  count          = 2
  subnet_id      = aws_subnet.private[count.index].id
  route_table_id = aws_route_table.private.id
}
