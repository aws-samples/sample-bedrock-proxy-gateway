# IAM Role for OIDC Federation
resource "aws_iam_role" "oauth_federation_role" {
  name = var.role_name

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Federated = var.oidc_provider_arn
        }
        Action = "sts:AssumeRoleWithWebIdentity"
        Condition = merge(
          {
            StringEquals = {
              "${var.oidc_provider_url}:aud" = var.jwt_audience
            }
          },
          var.restricted_role_session_name_suffix == null ? {} : {
            StringLike = {
              "sts:RoleSessionName" : [join("_", ["*", var.restricted_role_session_name_suffix])]
            }
          }
        )
      }
    ]
  })

  tags = var.tags
}

# Custom Bedrock policy with VPC endpoint condition
resource "aws_iam_role_policy" "oauth_bedrock_access" {
  #checkov:skip=CKV_AWS_355: "Ensure no IAM policies documents allow "*" as a statement's resource for restrictable actions"
  # skipping the above rule because the policy will be restricted at run-time via a temporary policy using Assume-role-with-web-identity

  name = "BedrockVPCEndpointAccess"
  role = aws_iam_role.oauth_federation_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      # Model invocation actions with VPC endpoint restriction
      merge(
        {
          Effect = "Allow"
          Action = [
            "bedrock:InvokeModel",
            "bedrock:InvokeModelWithResponseStream",
            "bedrock:Converse",
            "bedrock:ConverseStream",
            "bedrock:GetFoundationModel",
            "bedrock:GetFoundationModelAvailability",
            "bedrock:ListFoundationModels"
          ]
          Resource = "*"
        },
        var.allowed_source_vpc_endpoint_ids == null ? {} : {
          Condition = {
            StringEquals = {
              "aws:SourceVpce" = var.allowed_source_vpc_endpoint_ids
            }
          }
        }
      ),
      # ApplyGuardrail without VPC endpoint restriction (cross-account context issue)
      {
        Effect   = "Allow"
        Action   = ["bedrock:ApplyGuardrail"]
        Resource = "*"
      }
    ]
  })
}
