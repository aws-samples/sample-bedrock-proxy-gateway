"""Constants used throughout the application."""

from typing import Final

# Public paths that don't require authentication
# These endpoints are needed for health checks and API documentation
PUBLIC_PATHS = {"/", "/docs", "/openapi.json", "/redoc", "/health", "/health/valkey", "/debug"}

# Rate limiting constants
RATELIMIT_UNLIMITED: Final[int] = -1  # Indicates unlimited quota (no rate limiting)

# OAuth scope constants
SCOPE_BEDROCKPROXY_READ: Final[str] = "bedrockproxygateway:read"  # Read access to Bedrock proxy
SCOPE_BEDROCKPROXY_INVOKE: Final[str] = (
    "bedrockproxygateway:invoke"  # Invoke access to Bedrock proxy
)
SCOPE_BEDROCKPROXY_ADMIN: Final[str] = "bedrockproxygateway:admin"  # Admin access to Bedrock proxy

# JWT audience constant
JWT_AUDIENCE: Final[str] = "bedrockproxygateway"  # Bedrock Proxy Gateway audience

# Default allowed scopes - built from scope constants
DEFAULT_ALLOWED_SCOPES: Final[str] = (
    f"{SCOPE_BEDROCKPROXY_READ},{SCOPE_BEDROCKPROXY_INVOKE},{SCOPE_BEDROCKPROXY_ADMIN}"
)
