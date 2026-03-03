# =============================================================================
# Development Environment Configuration
# Copy this file to dev.local.tfvars and update with your actual values
# =============================================================================

# =============================================================================
# CORE CONFIGURATION
# =============================================================================
environment = "dev"
aws_region  = "us-east-1"

# =============================================================================
# ACCOUNT CONFIGURATION
# =============================================================================
# Replace with your actual AWS account IDs
shared_account_ids = "YOUR_SHARED_ACCOUNT_ID"
central_account_id = "YOUR_CENTRAL_ACCOUNT_ID"

# =============================================================================
# SECURITY CONFIGURATION
# =============================================================================
# Optional: S3 path to mTLS CA certificate bundle (leave empty to disable mTLS)
mtls_cert_ca_s3_path = ""

# =============================================================================
# OAuth/OIDC Configuration (Required)
# =============================================================================
# Configure your OAuth provider (Auth0, Okta, etc.)
# Example for Auth0:
#   oauth_jwks_url     = "https://<tenant>.auth0.com/.well-known/jwks.json"
#   oauth_issuer       = "https://<tenant>.auth0.com/"
#   jwt_audience       = "bedrockproxygateway"
#   jwt_allowed_scopes = "bedrockproxygateway:read,bedrockproxygateway:invoke,bedrockproxygateway:admin"

oauth_jwks_url     = "https://YOUR_OAUTH_PROVIDER/.well-known/jwks.json"
oauth_issuer       = "https://YOUR_OAUTH_PROVIDER/"
jwt_audience       = "bedrockproxygateway"
jwt_allowed_scopes = "bedrockproxygateway:read,bedrockproxygateway:invoke,bedrockproxygateway:admin"

# =============================================================================
# APPLICATION CONFIGURATION
# =============================================================================
# Optional: Specify custom Docker image tag (leave empty for latest)
gw_api_image_tag = ""
