# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

output "oidc_provider_arn" {
  description = "ARN of the OIDC provider"
  value       = aws_iam_openid_connect_provider.oauth_oidc.arn
}

output "oidc_provider_url" {
  description = "URL of the OIDC provider (without https:// and trailing slash for trust policy condition)"
  value       = trimprefix(trimsuffix(aws_iam_openid_connect_provider.oauth_oidc.url, "/"), "https://")
}
