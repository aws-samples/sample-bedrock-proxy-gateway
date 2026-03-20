# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

# Read VPC endpoint IDs written by central module
data "aws_ssm_parameter" "bedrock_vpce_id" {
  provider = aws.central
  name     = "/${var.service_name}/${var.environment}/central/bedrock-vpce-id"
}

data "aws_ssm_parameter" "bedrock_runtime_vpce_id" {
  provider = aws.central
  name     = "/${var.service_name}/${var.environment}/central/bedrock-runtime-vpce-id"
}
