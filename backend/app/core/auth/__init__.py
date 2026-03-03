"""Authentication package.

Contains JWT validation, JWKS handling, and authentication utilities
for securing API endpoints.
"""

from .jwks import jwks_cache
from .jwt_validator import validate_jwt_claims, validate_jwt_token

__all__ = [
    "validate_jwt_claims",
    "validate_jwt_token",
    "jwks_cache",
]
