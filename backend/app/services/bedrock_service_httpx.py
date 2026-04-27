# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Bedrock service using httpx + SigV4 for fully async, zero-boto3 request path."""

from __future__ import annotations

from datetime import UTC, datetime

import defusedxml.ElementTree as ET
import httpx
import orjson
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from botocore.credentials import Credentials
from config import config
from core.cache.memory_cache import get_cache, set_cache
from opentelemetry import trace

tracer = trace.get_tracer(__name__)

# Shared httpx client — connection pooling across all requests
_httpx_client: httpx.AsyncClient | None = None


def _get_httpx_client() -> httpx.AsyncClient:
    """Get or create the shared httpx client with connection pooling."""
    global _httpx_client
    if _httpx_client is None:
        _httpx_client = httpx.AsyncClient(
            timeout=httpx.Timeout(connect=5.0, read=90.0, write=10.0, pool=5.0),
            limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
        )
    return _httpx_client


class BedrockHttpxService:
    """Bedrock service using httpx for fully async HTTP calls with SigV4 signing.

    Replaces boto3 Session/Client creation per request with a shared httpx client
    and lightweight SigV4 request signing.
    """

    def __init__(self, logger) -> None:
        """Initialize Bedrock httpx service.

        Args:
        ----
            logger: Logger instance for logging
        """
        self.logger = logger
        self.aws_region = config.aws_region
        self.shared_role_name = config.shared_role_name
        self.sts_endpoint = (
            f"https://{config.sts_vpc_endpoint_dns}"
            if config.sts_vpc_endpoint_dns
            else f"https://sts.{self.aws_region}.amazonaws.com"
        )
        self.bedrock_endpoint = (
            f"https://{config.bedrock_runtime_vpc_endpoint_dns}"
            if config.bedrock_runtime_vpc_endpoint_dns
            else f"https://bedrock-runtime.{self.aws_region}.amazonaws.com"
        )
        self.role_session_suffix = config.app_hash

    async def get_credentials(
        self, client_id: str, account_id: str, jwt_token: str
    ) -> dict | None:
        """Get STS credentials from cache or via async httpx AssumeRoleWithWebIdentity.

        Args:
        ----
            client_id: Client identifier from JWT claims
            account_id: AWS account ID selected by rate limiting
            jwt_token: Raw JWT token for web identity federation

        Returns:
        -------
            Credentials dict with AccessKeyId, SecretAccessKey, SessionToken or None
        """
        cache_key = f"{client_id}:{account_id}"

        with tracer.start_as_current_span("aws.credentials") as span:
            span.set_attribute("credentials.client_id", client_id)
            span.set_attribute("credentials.account_id", account_id)

            # Try cache first
            cached = await get_cache(cache_key)
            if cached:
                span.set_attribute("credentials.source", "cache")
                return cached

            # Cache miss — async STS call (no SigV4 needed for AssumeRoleWithWebIdentity)
            span.set_attribute("credentials.source", "sts")
            role_arn = f"arn:aws:iam::{account_id}:role/{self.shared_role_name}"
            session_name = f"{config.environment}_{client_id}"
            if self.role_session_suffix:
                session_name = f"{session_name}_{self.role_session_suffix}"

            try:
                client = _get_httpx_client()
                sts_headers = {"Content-Type": "application/x-www-form-urlencoded"}
                # VPC endpoints require the regional STS Host header
                if config.sts_vpc_endpoint_dns:
                    sts_headers["Host"] = f"sts.{self.aws_region}.amazonaws.com"
                resp = await client.post(
                    self.sts_endpoint,
                    data={
                        "Action": "AssumeRoleWithWebIdentity",
                        "Version": "2011-06-15",
                        "RoleArn": role_arn,
                        "RoleSessionName": session_name,
                        "WebIdentityToken": jwt_token,
                    },
                    headers=sts_headers,
                )
                resp.raise_for_status()
            except httpx.HTTPStatusError as e:
                self.logger.error(f"STS AssumeRoleWithWebIdentity failed: {e.response.text[:200]}")
                return None
            except Exception as e:
                self.logger.error(f"STS request failed: {e}")
                return None

            # Parse XML response
            creds = self._parse_sts_response(resp.text)
            if not creds:
                return None

            # Cache with TTL based on expiration
            expiry = creds.get("Expiration")
            if expiry:
                ttl = int((expiry - datetime.now(UTC)).total_seconds())
                ttl = max(ttl - 60, 60)  # Refresh 60s before expiry
            else:
                ttl = 3500

            formatted = {
                "AccessKeyId": creds["AccessKeyId"],
                "SecretAccessKey": creds["SecretAccessKey"],
                "SessionToken": creds["SessionToken"],
            }
            await set_cache(cache_key, formatted, ttl)
            return formatted

    def _parse_sts_response(self, xml_text: str) -> dict | None:
        """Parse STS AssumeRoleWithWebIdentity XML response."""
        try:
            ns = {"sts": "https://sts.amazonaws.com/doc/2011-06-15/"}
            root = ET.fromstring(xml_text)
            creds_el = root.find(".//sts:Credentials", ns)
            if creds_el is None:
                self.logger.error(f"No Credentials in STS response: {xml_text[:200]}")
                return None

            expiration_str = creds_el.findtext("sts:Expiration", "", ns)
            expiration = (
                datetime.fromisoformat(expiration_str.replace("Z", "+00:00"))
                if expiration_str
                else None
            )

            return {
                "AccessKeyId": creds_el.findtext("sts:AccessKeyId", "", ns),
                "SecretAccessKey": creds_el.findtext("sts:SecretAccessKey", "", ns),
                "SessionToken": creds_el.findtext("sts:SessionToken", "", ns),
                "Expiration": expiration,
            }
        except ET.ParseError as e:
            self.logger.error(f"Failed to parse STS XML: {e}")
            return None

    def _sign_request(
        self, method: str, url: str, headers: dict, body: bytes, creds: dict
    ) -> dict:
        """Sign an HTTP request with SigV4 using botocore.

        Returns signed headers dict ready for httpx.
        """
        aws_creds = Credentials(
            access_key=creds["AccessKeyId"],
            secret_key=creds["SecretAccessKey"],
            token=creds["SessionToken"],
        )
        aws_request = AWSRequest(method=method, url=url, data=body, headers=headers)
        SigV4Auth(aws_creds, "bedrock", self.aws_region).add_auth(aws_request)
        return dict(aws_request.headers)

    async def converse(self, model_id: str, body: dict, creds: dict) -> dict:
        """Call Bedrock Converse API via httpx with SigV4 signing.

        Args:
        ----
            model_id: Bedrock model identifier
            body: Request body dict (messages, inferenceConfig, etc.)
            creds: AWS credentials dict from get_credentials

        Returns:
        -------
            Bedrock converse API response dict
        """
        url, body_bytes, headers = self._signed_bedrock_request(model_id, "converse", body, creds)
        client = _get_httpx_client()
        resp = await client.post(url, content=body_bytes, headers=headers)
        resp.raise_for_status()
        return orjson.loads(resp.content)

    def _signed_bedrock_request(
        self, model_id: str, operation: str, body: dict, creds: dict
    ) -> tuple[str, bytes, dict]:
        """Build a signed Bedrock request.

        Returns
        -------
            Tuple of (url, body_bytes, signed_headers)
        """
        url = f"{self.bedrock_endpoint}/model/{model_id}/{operation}"
        body_bytes = orjson.dumps(body)
        sign_headers = {"Content-Type": "application/json"}
        if config.bedrock_runtime_vpc_endpoint_dns:
            sign_headers["Host"] = f"bedrock-runtime.{self.aws_region}.amazonaws.com"
        headers = self._sign_request("POST", url, sign_headers, body_bytes, creds)
        return url, body_bytes, headers

    async def converse_stream(self, model_id: str, body: dict, creds: dict):
        """Call Bedrock ConverseStream API via httpx with SigV4 signing.

        Returns an httpx async stream context manager yielding raw EventStream bytes.

        Args:
        ----
            model_id: Bedrock model identifier
            body: Request body dict
            creds: AWS credentials dict from get_credentials

        Returns:
        -------
            httpx async stream context manager
        """
        url, body_bytes, headers = self._signed_bedrock_request(
            model_id, "converse-stream", body, creds
        )
        return _get_httpx_client().stream("POST", url, content=body_bytes, headers=headers)

    async def invoke_model(
        self, model_id: str, body_bytes: bytes, creds: dict, guardrail_params: dict | None = None
    ) -> bytes:
        """Call Bedrock InvokeModel API via httpx with SigV4 signing.

        Args:
        ----
            model_id: Bedrock model identifier
            body_bytes: Raw request body bytes
            creds: AWS credentials dict from get_credentials
            guardrail_params: Optional guardrail identifier/version/trace params

        Returns:
        -------
            Raw response body bytes
        """
        url = f"{self.bedrock_endpoint}/model/{model_id}/invoke"
        sign_headers: dict[str, str] = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if guardrail_params:
            if guardrail_params.get("guardrailIdentifier"):
                sign_headers["X-Amzn-Bedrock-GuardrailIdentifier"] = guardrail_params[
                    "guardrailIdentifier"
                ]
            if guardrail_params.get("guardrailVersion"):
                sign_headers["X-Amzn-Bedrock-GuardrailVersion"] = guardrail_params[
                    "guardrailVersion"
                ]
            if guardrail_params.get("trace"):
                sign_headers["X-Amzn-Bedrock-Trace"] = guardrail_params["trace"]
        if config.bedrock_runtime_vpc_endpoint_dns:
            sign_headers["Host"] = f"bedrock-runtime.{self.aws_region}.amazonaws.com"

        headers = self._sign_request("POST", url, sign_headers, body_bytes, creds)
        client = _get_httpx_client()
        resp = await client.post(url, content=body_bytes, headers=headers)
        resp.raise_for_status()
        return resp.content

    async def invoke_model_stream(
        self, model_id: str, body_bytes: bytes, creds: dict, guardrail_params: dict | None = None
    ):
        """Call Bedrock InvokeModelWithResponseStream API via httpx with SigV4 signing.

        Returns an httpx async stream context manager yielding raw EventStream bytes.

        Args:
        ----
            model_id: Bedrock model identifier
            body_bytes: Raw request body bytes
            creds: AWS credentials dict from get_credentials
            guardrail_params: Optional guardrail identifier/version/trace params

        Returns:
        -------
            httpx async stream context manager
        """
        url = f"{self.bedrock_endpoint}/model/{model_id}/invoke-with-response-stream"
        sign_headers: dict[str, str] = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if guardrail_params:
            if guardrail_params.get("guardrailIdentifier"):
                sign_headers["X-Amzn-Bedrock-GuardrailIdentifier"] = guardrail_params[
                    "guardrailIdentifier"
                ]
            if guardrail_params.get("guardrailVersion"):
                sign_headers["X-Amzn-Bedrock-GuardrailVersion"] = guardrail_params[
                    "guardrailVersion"
                ]
            if guardrail_params.get("trace"):
                sign_headers["X-Amzn-Bedrock-Trace"] = guardrail_params["trace"]
        if config.bedrock_runtime_vpc_endpoint_dns:
            sign_headers["Host"] = f"bedrock-runtime.{self.aws_region}.amazonaws.com"

        headers = self._sign_request("POST", url, sign_headers, body_bytes, creds)
        return _get_httpx_client().stream("POST", url, content=body_bytes, headers=headers)

    async def apply_guardrail(
        self,
        guardrail_id: str,
        guardrail_version: str,
        body: dict,
        creds: dict,
    ) -> dict:
        """Call Bedrock ApplyGuardrail API via httpx with SigV4 signing.

        Args:
        ----
            guardrail_id: Actual guardrail identifier
            guardrail_version: Guardrail version
            body: Request body dict (content, source, outputScope, etc.)
            creds: AWS credentials dict from get_credentials

        Returns:
        -------
            Bedrock apply guardrail API response dict
        """
        url = f"{self.bedrock_endpoint}/guardrail/{guardrail_id}/version/{guardrail_version}/apply"
        body_bytes = orjson.dumps(body)
        sign_headers = {"Content-Type": "application/json"}
        if config.bedrock_runtime_vpc_endpoint_dns:
            sign_headers["Host"] = f"bedrock-runtime.{self.aws_region}.amazonaws.com"
        headers = self._sign_request("POST", url, sign_headers, body_bytes, creds)

        client = _get_httpx_client()
        resp = await client.post(url, content=body_bytes, headers=headers)
        resp.raise_for_status()
        return orjson.loads(resp.content)


async def close_httpx_client() -> None:
    """Close the shared httpx client on application shutdown."""
    global _httpx_client
    if _httpx_client is not None:
        await _httpx_client.aclose()
        _httpx_client = None
