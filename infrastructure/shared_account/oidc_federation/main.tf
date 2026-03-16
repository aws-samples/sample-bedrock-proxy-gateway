# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

# OIDC Identity Provider for OAuth
resource "aws_iam_openid_connect_provider" "oauth_oidc" {
  url = var.oauth_provider_url

  client_id_list = [
    var.jwt_audience
  ]

  tags = var.tags
}
