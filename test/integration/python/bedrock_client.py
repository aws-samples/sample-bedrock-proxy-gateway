# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Bedrock Gateway client for integration tests."""

import logging
import os
import threading
from datetime import UTC, datetime, timedelta

import boto3
import requests
from botocore import UNSIGNED
from botocore.config import Config

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class BedrockProxyGateway:
    """Gateway client for Bedrock API with authentication and optional mTLS support."""

    def __init__(
        self,
        client_id,
        client_secret,
        mtls_cert_path=None,
        mtls_key_path=None,
        region="us-east-1",
        bedrock_runtime_endpoint_url=None,
        oauth_token_url=None,
        audience=None,
    ):
        self.client_id = client_id
        self.client_secret = client_secret
        self.mtls_cert_path = mtls_cert_path
        self.mtls_key_path = mtls_key_path
        self.region = region
        self.bedrock_runtime_endpoint_url = bedrock_runtime_endpoint_url or os.getenv(
            "GATEWAY_ENDPOINT_URL", "https://your-gateway-url.com"
        )
        self.oauth_token_url = oauth_token_url or os.getenv(
            "OAUTH_TOKEN_URL", "https://your-oauth-provider.com/oauth/token"
        )
        self.audience = audience or os.getenv("OAUTH_AUDIENCE")

        # Private Variable
        self._token = None
        self._expires = datetime.now(UTC) - timedelta(hours=1)
        self._lock = threading.Lock()

    def _fetch_token(self):
        try:
            payload = {
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "grant_type": "client_credentials",
                "scope": "bedrockproxygateway:invoke",
            }
            if self.audience:
                payload["audience"] = self.audience

            r = requests.post(self.oauth_token_url, data=payload)
            logger.debug(f"Token response status: {r.status_code}")

            r.raise_for_status()
            data = r.json()
            access_token = data["access_token"]
            expiration_seconds = int(data["expires_in"])
            expiry_time = datetime.now(UTC) + timedelta(seconds=expiration_seconds)

            logger.debug(f"Token expires in {expiration_seconds} seconds")
            logger.debug(f"Token prefix: {access_token[:20]}...")

            self._token = access_token
            self._expires = expiry_time

        except Exception as e:
            logger.error(f"Token fetch failed: {e}")
            raise RuntimeError(f"Failed to fetch JWT token: {e}") from e

    def get_token(self):
        """Get a valid authentication token, refreshing if necessary."""
        with self._lock:
            now = datetime.now(UTC)
            refresh_time = self._expires - timedelta(seconds=120)
            logger.debug(
                f"Current time: {now}, Token expires: {self._expires}, Refresh at: {refresh_time}"
            )

            if now > refresh_time:
                logger.debug("Token needs refresh")
                self._fetch_token()
            else:
                logger.debug("Using existing token")
            return self._token

    def get_bedrock_client(self, dummy_aws_creds=False):
        """Create and configure a Bedrock client with authentication and mTLS."""
        logger.debug(f"API URL: {self.bedrock_runtime_endpoint_url}")
        logger.debug(f"AWS Region: {self.region}")

        if dummy_aws_creds:
            logger.debug("Using dummy AWS credentials used for LiteLLM")
            bedrock = boto3.client(
                "bedrock-runtime",
                region_name=self.region,
                endpoint_url=self.bedrock_runtime_endpoint_url,
                aws_access_key_id="",
                aws_secret_access_key="",
                aws_session_token="",
                config=Config(client_cert=(self.mtls_cert_path, self.mtls_key_path))
                if self.mtls_cert_path and self.mtls_key_path
                else None,
            )
        else:
            logger.debug("Disabled the aws signature v4 for setup bedrock client")
            bedrock = boto3.client(
                "bedrock-runtime",
                region_name=self.region,
                endpoint_url=self.bedrock_runtime_endpoint_url,
                config=Config(
                    signature_version=UNSIGNED,
                    client_cert=(self.mtls_cert_path, self.mtls_key_path),
                )
                if self.mtls_cert_path and self.mtls_key_path
                else Config(signature_version=UNSIGNED),
            )

        def add_api_token(request, **_kwargs):
            token = f"Bearer {self.get_token()}"
            logger.debug(f"Adding Authorization header: {token[:30]}...")
            request.headers.add_header("Authorization", token)
            return request

        bedrock.meta.events.register("before-sign.bedrock-runtime.*", add_api_token)
        logger.debug("Bedrock client created and configured")
        return bedrock
