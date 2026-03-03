"""Bedrock service for managing multi-account client access."""

from __future__ import annotations

import asyncio
from datetime import datetime
from functools import partial

import boto3
import jwt
from config import config
from core.cache.memory_cache import get_cache, set_cache
from opentelemetry import context, trace

ROLE_SESSION_NAME_SUFFIX_SEPARATOR = "_"
tracer = trace.get_tracer(__name__)


class AsyncBedrockClient:
    """Async wrapper for boto3 bedrock client."""

    def __init__(self, client):
        """Initialize with sync boto3 client."""
        self.client = client
        self.loop = None

    async def __aenter__(self):
        """Async context manager entry."""
        self.loop = asyncio.get_event_loop()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        pass

    def _run_with_context(self, func, ctx):
        """Execute function with OpenTelemetry context in thread."""
        token = context.attach(ctx)
        try:
            return func()
        finally:
            context.detach(token)

    async def converse(self, **kwargs):
        """Async wrapper for converse method."""
        ctx = context.get_current()
        func = partial(self.client.converse, **kwargs)
        return await self.loop.run_in_executor(None, self._run_with_context, func, ctx)

    async def converse_stream(self, **kwargs):
        """Async wrapper for converse_stream method."""
        ctx = context.get_current()
        func = partial(self.client.converse_stream, **kwargs)
        return await self.loop.run_in_executor(None, self._run_with_context, func, ctx)

    async def invoke_model(self, **kwargs):
        """Async wrapper for invoke_model method."""
        ctx = context.get_current()
        func = partial(self.client.invoke_model, **kwargs)
        return await self.loop.run_in_executor(None, self._run_with_context, func, ctx)

    async def invoke_model_with_response_stream(self, **kwargs):
        """Async wrapper for invoke_model_with_response_stream method."""
        ctx = context.get_current()
        func = partial(self.client.invoke_model_with_response_stream, **kwargs)
        return await self.loop.run_in_executor(None, self._run_with_context, func, ctx)

    async def apply_guardrail(self, **kwargs):
        """Async wrapper for apply_guardrail method."""
        ctx = context.get_current()
        func = partial(self.client.apply_guardrail, **kwargs)
        return await self.loop.run_in_executor(None, self._run_with_context, func, ctx)


class BedrockService:
    """Manages Bedrock client creation with multi-account routing and credential caching."""

    def __init__(self, session: boto3.Session, logger) -> None:
        """Initialize Bedrock service.

        Args:
        ----
            session: Boto3 session to use for creating clients
            logger: Logger instance for logging
        """
        self.session = session
        self.logger = logger

        # AWS configuration
        self.shared_role_name = config.shared_role_name
        self.aws_region = config.aws_region

        # VPC endpoint configuration
        self.bedrock_runtime_vpc_endpoint_dns = config.bedrock_runtime_vpc_endpoint_dns
        self.sts_vpc_endpoint_dns = config.sts_vpc_endpoint_dns
        self.sts_role_session_name_suffix = config.app_hash

    async def get_authenticated_client(
        self, jwt_token: str, account_id: str | None = None
    ) -> AsyncBedrockClient | None:
        """Get authenticated Bedrock client for JWT token with account routing.

        Args:
        ----
            jwt_token: JWT token for authorization
            account_id: AWS account ID selected by rate limiting middleware

        Returns:
        -------
            Async Bedrock runtime client or None if creation fails
        """
        if not jwt_token:
            return None

        if not account_id:
            self.logger.warning(
                "No account_id provided - account routing handled by rate limiting"
            )
            return None

        try:
            claims = jwt.decode(jwt_token, options={"verify_signature": False})
            client_id = claims.get("client_id") or claims.get("sub") or "unknown"

            # Use account selected by rate limiting middleware
            cache_key = f"{client_id}:{account_id}"
            credentials = await self._get_credentials(cache_key, account_id, client_id, jwt_token)

            if not credentials:
                return None

            return await self._create_async_bedrock_client(credentials)

        except Exception as e:
            self.logger.error(f"Failed to create bedrock client: {e}")
            return None

    async def _get_credentials(
        self, cache_key: str, account_id: str, client_id: str, jwt_token: str
    ) -> dict | None:
        """Get credentials from cache or perform STS assume role."""
        with tracer.start_as_current_span("aws.credentials") as span:
            span.set_attribute("credentials.client_id", client_id)
            span.set_attribute("credentials.account_id", account_id)
            span.set_attribute("credentials.cache_type", "memory")

            # Try cache first
            cached_credentials = await get_cache(cache_key)
            if cached_credentials:
                span.set_attribute("credentials.source", "memory")
                span.set_attribute("credentials.cache_hit", True)
                return cached_credentials

            # Cache miss - perform STS assume role
            span.set_attribute("credentials.source", "sts")
            span.set_attribute("credentials.cache_hit", False)

            role_arn = f"arn:aws:iam::{account_id}:role/{self.shared_role_name}"

            sts_client = self.session.client(
                "sts",
                region_name=self.aws_region,
                endpoint_url=f"https://{self.sts_vpc_endpoint_dns}"
                if self.sts_vpc_endpoint_dns
                else None,
            )

            # Build role session name
            base_session_name = f"{config.environment}_{client_id}"
            if self.sts_role_session_name_suffix:
                role_session_name = f"{base_session_name}{ROLE_SESSION_NAME_SUFFIX_SEPARATOR}{self.sts_role_session_name_suffix}"
            else:
                role_session_name = base_session_name

            response = sts_client.assume_role_with_web_identity(
                RoleArn=role_arn,
                RoleSessionName=role_session_name,
                WebIdentityToken=jwt_token,
            )

            credentials = response["Credentials"]

            # Cache credentials
            expiration = credentials["Expiration"]
            ttl_seconds = int((expiration - datetime.now(expiration.tzinfo)).total_seconds())

            # Format credentials for caching
            formatted_credentials = {
                "AccessKeyId": credentials.get("AccessKeyId", ""),
                "SecretAccessKey": credentials.get("SecretAccessKey", ""),
                "SessionToken": credentials.get("SessionToken", ""),
            }
            await set_cache(cache_key, formatted_credentials, ttl_seconds)

            return credentials

    async def _create_async_bedrock_client(self, credentials: dict) -> AsyncBedrockClient:
        """Create async bedrock client with given credentials."""
        shared_session = boto3.Session(  # nosec B106
            aws_access_key_id=credentials["AccessKeyId"],
            aws_secret_access_key=credentials["SecretAccessKey"],
            aws_session_token=credentials["SessionToken"],
        )

        client = shared_session.client(
            "bedrock-runtime",
            region_name=self.aws_region,
            endpoint_url=f"https://{self.bedrock_runtime_vpc_endpoint_dns}"
            if self.bedrock_runtime_vpc_endpoint_dns
            else None,
        )

        return AsyncBedrockClient(client)
