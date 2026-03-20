# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

output "valkey_endpoint" {
  value = aws_elasticache_serverless_cache.sts_cache.endpoint
}
