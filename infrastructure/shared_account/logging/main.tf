# Bedrock model invocation logging configuration
# Logs are written directly to the central account's CloudWatch Log Group
# via cross-account resource policy

# Note: Bedrock service automatically creates log streams in the central account's
# /aws/bedrock/modelinvocations log group when model logging is enabled.
# The central account's CloudWatch Logs resource policy grants PutLogEvents permission
# to shared accounts.
