"""JWT validation module."""

import logging
import time

import jwt
from config import config
from jwt import PyJWKClient

logger = logging.getLogger(__name__)

# Global JWKS client with caching
_jwks_client = None


def _get_jwks_client():
    """Get or create JWKS client."""
    global _jwks_client
    if _jwks_client is None and config.jwks_url:
        _jwks_client = PyJWKClient(config.jwks_url, cache_keys=True, lifespan=86400)
    return _jwks_client


def validate_jwt_token(token: str) -> dict:
    """Validate JWT token integrity and claims.

    Args:
    ----
        token (str): JWT token to validate.

    Returns:
    -------
        dict: Decoded JWT claims if validation successful.

    Raises:
    ------
        ValueError: If token is invalid, expired, or has wrong audience.
    """
    try:
        # Fetch RSA public key from JWKS endpoint (cached for performance)
        if not config.jwks_url:
            raise ValueError("JWKS URL not configured")

        jwks_client = _get_jwks_client()
        if not jwks_client:
            raise ValueError("Failed to initialize JWKS client")

        # Get the signing key from the JWT header
        signing_key = jwks_client.get_signing_key_from_jwt(token)

        # Decode JWT and validate signature, audience, expiration, and not-before claims
        decoded_token = jwt.decode(
            token,
            key=signing_key.key,
            algorithms=["RS256", "RS384", "RS512"],
            audience=config.jwt_audience if config.jwt_audience else None,
            issuer=config.oauth_issuer if config.oauth_issuer else None,
            options={
                "verify_aud": bool(config.jwt_audience),
                "verify_iss": bool(config.oauth_issuer),
                "verify_exp": True,
                "verify_nbf": True,
            },
        )

        return decoded_token

    except jwt.ExpiredSignatureError:
        raise ValueError("Token has expired") from None
    except jwt.InvalidAudienceError:
        raise ValueError(f"Invalid audience. Expected: {config.jwt_audience}") from None
    except jwt.InvalidIssuerError:
        raise ValueError(f"Invalid issuer. Expected: {config.oauth_issuer}") from None
    except jwt.InvalidTokenError as e:
        raise ValueError(f"Invalid token: {str(e)}") from None


def validate_jwt_claims(claims: dict) -> dict:
    """Validate JWT claims and extract client info.

    Args:
    ----
        claims (dict): Decoded JWT claims to validate.

    Returns:
    -------
        dict: Client information extracted from claims including client_id and scope.

    Raises:
    ------
        ValueError: If required claims are missing, scope is invalid, or token timing
            is invalid.
    """
    # Extract client identifier - support multiple claim names
    client_id = claims.get("client_id") or claims.get("sub") or claims.get("azp")

    # Extract scope - support both string and array formats
    scope = claims.get("scope")
    if isinstance(scope, list):
        scope = " ".join(scope)

    # Validate required claims are present
    if not client_id:
        raise ValueError("Missing required claims: client_id, sub, or azp")

    if not scope:
        raise ValueError("Missing required claim: scope")

    # Validate scope against allowed scopes (check if any allowed scope is present)
    user_scopes = scope.split() if isinstance(scope, str) else [scope]
    if not any(allowed_scope in user_scopes for allowed_scope in config.allowed_scopes):
        raise ValueError(f"Invalid scope: {scope}. Allowed: {config.allowed_scopes}")

    # Additional time validation beyond JWT library checks
    current_time = time.time()
    nbf = claims.get("nbf", 0)
    exp = claims.get("exp", 0)

    if not (nbf <= current_time <= exp):
        raise ValueError("Token not valid for current time")

    # Return normalized client context for downstream processing
    # Extract organizational information - support multiple claim names
    org_id = claims.get("org") or claims.get("organization") or claims.get("website") or client_id

    return {
        "client_id": client_id,
        "scope": scope,
        "orgId": org_id,
    }
