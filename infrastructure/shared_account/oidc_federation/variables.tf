variable "oauth_provider_url" {
  description = "OAuth provider URL (e.g., https://tenant.auth0.com/)"
  type        = string
}

variable "jwt_audience" {
  description = "JWT audience claim (API identifier)"
  type        = string
}


variable "tags" {
  description = "Tags to apply to resources"
  type        = map(string)
  default     = {}
}
