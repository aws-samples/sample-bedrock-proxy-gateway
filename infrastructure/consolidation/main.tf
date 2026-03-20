# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

module "guardrail_consolidation" {
  source = "../modules/guardrail_registry"

  common      = local.common
  common_tags = local.common_tags
}
