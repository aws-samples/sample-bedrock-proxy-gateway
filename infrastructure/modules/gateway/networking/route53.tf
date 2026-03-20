# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

# =============================================================================
# ROUTE53 HOSTED ZONE
# =============================================================================

resource "aws_route53_zone" "main" {
  name = "${var.common.app_id}-${var.common.environment}.${var.common.aws_region}.aws.internal"

  vpc {
    vpc_id = aws_vpc.main.id
  }

  tags = merge(
    var.common_tags,
    {
      Name = "${var.common.app_id}-${var.common.environment}-hosted-zone"
    }
  )
}
