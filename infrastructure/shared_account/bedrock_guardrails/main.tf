resource "aws_bedrock_guardrail" "bedrock_guardrails" {
  for_each                  = toset(keys(local.guardrail_profiles))
  name                      = "${local.guardrail_prefix}-${each.value}-guardrails"
  description               = "Guardrail with '${each.value}' profile for ${local.guardrail_prefix}."
  blocked_input_messaging   = local.guardrail_profiles[each.value].messages.blocked_input
  blocked_outputs_messaging = local.guardrail_profiles[each.value].messages.blocked_output

  dynamic "content_policy_config" {
    for_each = lookup(local.guardrail_profiles[each.value], "content_filters", null) == null ? [] : [1]
    content {
      dynamic "filters_config" {
        for_each = local.guardrail_profiles[each.value].content_filters
        content {
          input_strength  = filters_config.value.input_strength
          output_strength = filters_config.value.output_strength
          type            = filters_config.value.type
        }
      }
    }
  }

  contextual_grounding_policy_config {
    filters_config {
      threshold = local.guardrail_profiles[each.value].contextual_grounding.relevance_threshold
      type      = "RELEVANCE"
    }
  }

  word_policy_config {
    dynamic "managed_word_lists_config" {
      for_each = local.guardrail_profiles[each.value].forbidden_words.managed_lists
      content {
        type = managed_word_lists_config.value.type
      }
    }
  }

  tags = merge(var.tags, { profile = each.value })
}

resource "aws_bedrock_guardrail_version" "bedrock_guadrail_versions" {
  for_each      = toset(keys(local.guardrail_profiles))
  guardrail_arn = aws_bedrock_guardrail.bedrock_guardrails[each.value].guardrail_arn
  description   = "Guardrail version with '${each.value}' profile."
  depends_on    = [aws_bedrock_guardrail.bedrock_guardrails]
  lifecycle {
    replace_triggered_by = [aws_bedrock_guardrail.bedrock_guardrails[each.key]]
  }
}



##########################
# Logging confgiguration #
##########################

# IAM Role for Bedrock Logging
resource "aws_iam_role" "bedrock_logging_role" {
  name = var.bedrock_logging_role_name

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "bedrock.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })

  tags = var.tags
}

# IAM Policy for Bedrock to write to CloudWatch (cross-account to central account)
resource "aws_iam_role_policy" "bedrock_logging_policy" {
  name = var.bedrock_logging_policy_name
  role = aws_iam_role.bedrock_logging_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = [
          "arn:aws:logs:${var.common.aws_region}:${var.central_account_id}:log-group:${var.log_group_name}:*"
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "kms:Encrypt",
          "kms:GenerateDataKey*",
          "kms:DescribeKey"
        ]
        Resource = [
          "arn:aws:kms:${var.common.aws_region}:${var.central_account_id}:key/*"
        ]
      }
    ]
  })
}

# Bedrock Logging Configuration
resource "aws_bedrock_model_invocation_logging_configuration" "bedrock_logging" {
  logging_config {
    embedding_data_delivery_enabled = true
    image_data_delivery_enabled     = true
    text_data_delivery_enabled      = true

    cloudwatch_config {
      log_group_name = var.log_group_name
      role_arn       = aws_iam_role.bedrock_logging_role.arn
    }
  }
}

##########################
# Guardrail Registry     #
##########################

# Write guardrails to central account SSM for consolidation
resource "aws_ssm_parameter" "guardrails_registry" {
  #checkov:skip=CKV2_AWS_34: "Encryption not required for non-sensitive guardrail metadata"
  provider = aws.central

  name = "/${var.common.service_name}/${var.common.environment}/guardrails/account/${var.common.aws_account_id}"
  type = "String"
  value = jsonencode({
    for logical_id, guardrail in aws_bedrock_guardrail.bedrock_guardrails :
    logical_id => {
      guardrail_id = guardrail.guardrail_id
      version      = aws_bedrock_guardrail_version.bedrock_guadrail_versions[logical_id].version
    }
  })

  tags = merge(var.tags, {
    Name        = "guardrails-registry-${var.common.aws_account_id}"
    Environment = var.common.environment
  })
}
