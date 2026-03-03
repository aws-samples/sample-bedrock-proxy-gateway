"""Configuration module."""

import logging
import os

from util.constants import DEFAULT_ALLOWED_SCOPES
from util.constants import JWT_AUDIENCE as DEFAULT_JWT_AUDIENCE

logger = logging.getLogger(__name__)


class Config:
    """Application configuration.

    Manages environment-specific configuration for JWT validation and API settings.
    Supports configurable OAuth 2.0 providers for flexible authentication.

    Attributes
    ----------
        environment: Current deployment environment (dev or test).
        oauth_provider_name: Name of the OAuth provider.
        oauth_token_endpoint: OAuth token endpoint URL.
        jwks_url: URL for JSON Web Key Set endpoint for JWT validation.
        oauth_issuer: OAuth token issuer.
        jwt_audience: Expected audience claim in JWT tokens.
        allowed_scopes: List of permitted scopes for API access.
        valkey_url: Valkey connection URL for rate limiting.
        rate_limiting_enabled: Whether rate limiting is enabled.
        rate_limit_config: JSON configuration for rate limits.
    """

    def __init__(self):
        """Initialize configuration based on environment variables.

        Sets up OAuth 2.0 and JWT validation parameters from environment variables.
        """
        self.environment = os.getenv("ENVIRONMENT", "dev")
        self.aws_region = os.getenv("AWS_REGION", os.getenv("DEFAULT_AWS_REGION", "us-east-1"))
        self.log_level = os.getenv("LOG_LEVEL", "INFO").upper()

        # OAuth 2.0 Provider Configuration
        self.oauth_provider_name = os.getenv("OAUTH_PROVIDER_NAME", "generic")
        self.oauth_token_endpoint = os.getenv("OAUTH_TOKEN_ENDPOINT", "")
        self.jwks_url = os.getenv("OAUTH_JWKS_URL", "")
        self.oauth_issuer = os.getenv("OAUTH_ISSUER", "")

        # JWT validation parameters
        self.jwt_audience = os.getenv("JWT_AUDIENCE", DEFAULT_JWT_AUDIENCE)
        allowed_scopes_str = os.getenv("JWT_ALLOWED_SCOPES", DEFAULT_ALLOWED_SCOPES)
        self.allowed_scopes = [scope.strip() for scope in allowed_scopes_str.split(",")]

        # AWS Service Configuration
        self.shared_role_name = os.getenv("SHARED_ROLE_NAME", "shared-account-role")
        self.bedrock_runtime_vpc_endpoint_dns = os.getenv("BEDROCK_RUNTIME_VPC_ENDPOINT_DNS", "")
        self.sts_vpc_endpoint_dns = os.getenv("STS_VPC_ENDPOINT_DNS", "")
        self.shared_account_ids = os.getenv("SHARED_ACCOUNT_IDS", "")
        self.app_hash = os.getenv("APP_HASH", "")

        # Observability Configuration
        self.otel_sdk_disabled = os.getenv("OTEL_SDK_DISABLED", "false").lower() == "true"
        self.otel_service_name = os.getenv("OTEL_SERVICE_NAME", "bedrock-gateway")
        self.otel_exporter_otlp_endpoint = os.getenv(
            "OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317"
        )

        # Guardrail Configuration
        self.guardrail_refresh_interval = int(os.getenv("GUARDRAIL_REFRESH_INTERVAL", "300"))

        # Rate limiting configuration
        self.valkey_url = os.getenv("VALKEY_URL", "redis://localhost:6379")
        self.valkey_ssl = self.environment != "local"

        # ElastiCache IAM authentication
        self.elasticache_cluster_name = os.getenv("ELASTICACHE_CLUSTER_NAME")
        self.elasticache_username = os.getenv("ELASTICACHE_USERNAME")
        self.elasticache_use_iam = os.getenv("ELASTICACHE_USE_IAM", "false").lower() == "true"

        default_rate_limiting = "false" if self.environment == "dev" else "true"
        self.rate_limiting_enabled = (
            os.getenv("RATE_LIMITING_ENABLED", default_rate_limiting).lower() == "true"
        )
        self.rate_limit_config = self._load_rate_limit_config()

    def _load_rate_limit_config(self) -> str:
        """Load rate limit configuration from YAML file based on environment.

        Checks for .local.yaml files first (for personal testing), then falls back
        to regular files. This allows keeping personal configs out of version control.
        """
        import json
        from pathlib import Path

        import yaml

        # Map environment to config file
        config_file_map = {
            "dev": "dev.yaml",
            "test": "test.yaml",
        }
        config_file = config_file_map.get(self.environment, "base.yaml")
        config_dir = Path(__file__).parent / "core" / "rate_limit" / "config"

        # Check for .local version first (for personal testing)
        local_config_file = config_file.replace(".yaml", ".local.yaml")
        local_config_path = config_dir / local_config_file
        config_path = config_dir / config_file

        # Prefer .local file if it exists
        if local_config_path.exists():
            config_path = local_config_path

        try:
            with open(config_path) as f:
                config_data = yaml.safe_load(f)
                return json.dumps(config_data)
        except Exception as e:
            logger.warning(f"Failed to load rate limit config from {config_path}: {e}")
            return "{}"


# Global config instance
config = Config()
