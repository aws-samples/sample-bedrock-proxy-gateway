# =============================================================================
# SHARED CONFIGURATION OBJECTS
# =============================================================================

variable "common" {
  type = object({
    app_id         = string
    aws_region     = string
    aws_account_id = string
    environment    = string
    service_name   = string
  })
  description = "Common variables shared across all modules"
}

variable "common_tags" {
  type        = map(string)
  description = "Common tags applied to all resources"
}
