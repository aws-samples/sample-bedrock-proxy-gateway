# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

resource "aws_elasticache_serverless_cache" "sts_cache" {
  engine             = "valkey"
  name               = local.cache_name
  kms_key_id         = aws_kms_key.val_key_kms_key.arn
  security_group_ids = [aws_security_group.sts_cache_security_group.id]
  subnet_ids         = var.private_subnet_ids
}

resource "aws_security_group" "sts_cache_security_group" {
  # TODO: Restrict security group egress to only required VPC endpoints e.g. KMS VPCe
  # TODO: Use security group chaining to allow inbound connections from required security groups instead of VPC CIDR
  # checkov:no-skip=CKV_AWS_382: "TODO: Ensure no security groups allow egress from 0.0.0.0:0 to port -1"
  # checkov:skip=CKV2_AWS_5: "[F/P] Security group attached to the Elasticache resources above."

  name        = local.cache_security_group_name
  description = "Security group for Elasticache Valkey"
  vpc_id      = var.vpc_id

  ingress {
    from_port   = 6379
    to_port     = 6379
    protocol    = "tcp"
    cidr_blocks = [var.vpc_cidr_block]
    description = "Allow inbound connection from VPC"
  }
}
