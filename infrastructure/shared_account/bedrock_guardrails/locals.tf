locals {
  # Guardrail naming with v2 suffix to avoid conflicts with v1 guardrails
  guardrail_prefix = "${var.common.environment}-v2"

  guardrail_profiles_path = "${path.module}/profiles"
  guardrail_profiles      = { for profile in fileset(local.guardrail_profiles_path, "*.yaml") : trimsuffix(profile, ".yaml") => yamldecode(file(join("/", [local.guardrail_profiles_path, profile]))) }
}
