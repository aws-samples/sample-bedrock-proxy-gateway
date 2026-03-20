# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Load-test Bedrock converse API through the proxy gateway with Locust.

Usage:
    locust -f locust.py --users 1 --spawn-rate 10 --run-time 30s --headless --only-summary
    locust -f locust.py --users 16 --spawn-rate 10 --run-time 3m --headless

"""

import json
import os
import time
from datetime import datetime, timedelta
from pathlib import Path

import boto3
import requests
from botocore import UNSIGNED
from botocore.config import Config
from dotenv import load_dotenv
from locust import User, events, task

# Load environment from .env.{ENVIRONMENT} at repo root
ENVIRONMENT = os.getenv("ENVIRONMENT", "dev")
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(REPO_ROOT / f".env.{ENVIRONMENT}")

AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
API_URL = os.getenv("GATEWAY_API_URL", "https://your-gateway-url.com")

RESULT_FOLDER = f"./tmp_results/{datetime.now().strftime('%m__%d___%H__%M__%S')}"
SLOW_TRACE_FILE = f"{RESULT_FOLDER}/slow_traces_results.csv"
SLOW_TRACE_THRESHOLD_VALUE_IN_MS = 2000
TEST_METADATA_FILE = f"{RESULT_FOLDER}/test_metadata.txt"

BEDROCK_MODEL_ID_LIST = [
    "us.amazon.nova-lite-v1:0",
    "us.meta.llama3-3-70b-instruct-v1:0",
]

PROMPT = "how are you? tell me a story about Juventus"

# Global counter for successful invocations
successful_invocations = 0
successful_invocations_by_model = dict.fromkeys(BEDROCK_MODEL_ID_LIST, 0)

# Global test timing variables
test_start_datetime = None
test_end_datetime = None

# Create results directory and CSV header
os.makedirs(RESULT_FOLDER, exist_ok=True)
with open(SLOW_TRACE_FILE, "w") as f:
    f.write("trace_id,e2e_ms,bedrock_ms,gateway_overhead_ms\n")

# Initialize test metadata file
with open(TEST_METADATA_FILE, "w") as f:
    f.write("=== Load Test Metadata ===\n")
    f.write(f"Test Start Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    f.write("Token Expiration: (will be updated when first token is generated)\n")
    f.write("Test Finish Time: (will be updated when test completes)\n")
    f.write("Total Successful Invocations: (will be updated when test completes)\n")
    for model_id in BEDROCK_MODEL_ID_LIST:
        f.write(
            f"Total Successful Invocations for {model_id}: (will be updated when test completes)\n"
        )


def on_test_start(environment, **kwargs):  # noqa: ARG001
    """Event handler for when the test starts."""
    global test_start_datetime
    test_start_datetime = datetime.now()
    print(f"🚀 Load test started at {test_start_datetime.strftime('%Y-%m-%d %H:%M:%S')}")


def on_test_stop(environment, **kwargs):  # noqa: ARG001
    """Event handler for when the test stops."""
    global test_end_datetime
    test_end_datetime = datetime.now()
    test_finish_time = test_end_datetime.strftime("%Y-%m-%d %H:%M:%S")
    print(f"🏁 Load test finished at {test_finish_time}")
    print(f"📊 Total successful invocations: {successful_invocations}")

    try:
        with open(TEST_METADATA_FILE) as f:
            content = f.read()

        content = content.replace(
            "Test Finish Time: (will be updated when test completes)",
            f"Test Finish Time: {test_finish_time}",
        )
        content = content.replace(
            "Total Successful Invocations: (will be updated when test completes)",
            f"Total Successful Invocations: {successful_invocations}",
        )
        for model_id in BEDROCK_MODEL_ID_LIST:
            content = content.replace(
                f"Total Successful Invocations for {model_id}: (will be updated when test completes)",
                f"Total Successful Invocations for {model_id}: {successful_invocations_by_model[model_id]}",
            )

        with open(TEST_METADATA_FILE, "w") as f:
            f.write(content)
    except Exception as e:
        print(f"Error updating test metadata file: {e}")


events.test_start.add_listener(on_test_start)
events.test_stop.add_listener(on_test_stop)


class BedrockUser(User):
    """Simulates a Locust user that sends converse requests through the proxy gateway."""

    def _fetch_oauth_token(self):
        """Fetch OAuth credentials from Secrets Manager and request an access token.

        Returns
        -------
            tuple: (access_token, expires_in) from the OAuth provider.
        """
        secret_id = os.getenv("GATEWAY_SECRET_ID", "")
        if not secret_id:
            raise ValueError("GATEWAY_SECRET_ID not set in .env file")

        session = boto3.Session(
            profile_name=os.getenv("AWS_PROFILE"),
            region_name=AWS_REGION,
        )
        secret = json.loads(
            session.client("secretsmanager").get_secret_value(SecretId=secret_id)["SecretString"]
        )

        # Setup mTLS certificates if available
        cert_path = os.getenv("MTLS_CERT_PATH")
        key_path = os.getenv("MTLS_KEY_PATH")
        if cert_path and key_path:
            self.cert_config = (cert_path, key_path)
        else:
            self.cert_config = None

        payload = {
            "client_id": secret["client_id"],
            "client_secret": secret["client_secret"],  # noqa: S105
            "grant_type": "client_credentials",
            "audience": secret.get("audience", ""),
            "scope": "bedrockproxygateway:invoke",
        }

        response = requests.post(secret["token_url"], data=payload, cert=self.cert_config)
        response.raise_for_status()
        token_data = response.json()
        return token_data["access_token"], token_data.get("expires_in", 3600)

    def _update_metadata_expiration(self, expires_at, expires_in):
        """Update the test metadata file with token expiration info."""
        try:
            with open(TEST_METADATA_FILE) as f:
                content = f.read()

            token_info = f"Token Expiration: {expires_at.strftime('%Y-%m-%d %H:%M:%S')} (expires in {expires_in}s)"
            content = content.replace(
                "Token Expiration: (will be updated when first token is generated)",
                token_info,
            )

            with open(TEST_METADATA_FILE, "w") as f:
                f.write(content)
        except Exception as e:
            print(f"Error updating test metadata file with token info: {e}")

    def generate_token(self):
        """Generate an access token from OAuth2 endpoint.

        Returns
        -------
            str: Bearer token string for Authorization header.
        """
        token, expires_in = self._fetch_oauth_token()
        self.token_expires_at = datetime.now() + timedelta(seconds=expires_in)
        self._update_metadata_expiration(self.token_expires_at, expires_in)
        return f"Bearer {token}"

    def is_token_expired(self):
        """Check if the current token is expired or about to expire."""
        if not hasattr(self, "token_expires_at"):
            return True

        time_until_expiry = (self.token_expires_at - datetime.now()).total_seconds()

        if time_until_expiry <= 0:
            print(f"⚠️  TOKEN EXPIRED at {self.token_expires_at.strftime('%Y-%m-%d %H:%M:%S')}")
            return True
        elif time_until_expiry <= 60:
            print(
                f"⚠️  TOKEN EXPIRES SOON in {int(time_until_expiry)} seconds at {self.token_expires_at.strftime('%Y-%m-%d %H:%M:%S')}"
            )
        return False

    def create_bedrock_client(self, token):
        """Create a Bedrock runtime client with the provided auth token."""
        bedrock = boto3.client(
            "bedrock-runtime",
            region_name=AWS_REGION,
            endpoint_url=API_URL,
            config=Config(signature_version=UNSIGNED, client_cert=self.cert_config),
        )

        def add_api_token(request, **kwargs):  # noqa: ARG001
            request.headers.add_header("Authorization", token)
            return request

        bedrock.meta.events.register("before-sign.bedrock-runtime.*", add_api_token)
        return bedrock

    def on_start(self):
        """Initialize the user session by authenticating and creating the Bedrock client."""
        token = self.generate_token()
        self.model_iterator = 0
        self.bedrock = self.create_bedrock_client(token)

    @task
    def converse_gateway(self) -> None:
        """Send a converse request through the gateway and measure gateway overhead."""
        global successful_invocations, successful_invocations_by_model

        e2e_start_time = time.perf_counter_ns()

        try:
            resp = self.bedrock.converse(
                modelId=BEDROCK_MODEL_ID_LIST[self.model_iterator],
                messages=[{"role": "user", "content": [{"text": PROMPT}]}],
                inferenceConfig={"maxTokens": 256},
            )

            e2e_end_time = time.perf_counter_ns()
            e2e_ms = (e2e_end_time - e2e_start_time) / 1_000_000.0
            bedrock_ms = float(resp.get("metrics", {}).get("latencyMs", 0.0))
            gateway_overhead_ms = e2e_ms - bedrock_ms

            successful_invocations += 1
            current_model = BEDROCK_MODEL_ID_LIST[self.model_iterator]
            successful_invocations_by_model[current_model] += 1

            self.model_iterator = (self.model_iterator + 1) % len(BEDROCK_MODEL_ID_LIST)

            # Persist slow traces
            if gateway_overhead_ms >= SLOW_TRACE_THRESHOLD_VALUE_IN_MS:
                trace_id = (
                    resp.get("ResponseMetadata", {})
                    .get("HTTPHeaders", {})
                    .get("x-trace-id", "none")
                )
                with open(SLOW_TRACE_FILE, "a", encoding="utf-8") as f:
                    f.write(f"{trace_id},{e2e_ms},{bedrock_ms},{gateway_overhead_ms:.3f}\n")

            events.request.fire(
                request_type="load",
                name="gateway_overhead",
                response_time=int(gateway_overhead_ms),
                response_length=0,
                exception=None,
                context={},
            )

        except Exception as exc:
            if "403" in str(exc) or "Forbidden" in str(exc):
                print(f"🛑 CRITICAL: 403 Forbidden error detected - {exc}")
                print("🛑 Stopping test due to authentication failure...")
                try:
                    with open(TEST_METADATA_FILE, "a") as f:
                        f.write(
                            f"\n🛑 TEST STOPPED DUE TO 403 ERROR at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                        )
                        f.write(f"Error: {exc}\n")
                except Exception:
                    pass
                self.environment.runner.quit()
                return

            print(f"Error: {exc}")
            events.request.fire(
                request_type="error",
                name="error",
                response_time=int((time.perf_counter_ns() - e2e_start_time) / 1_000_000.0),
                response_length=0,
                exception=exc,
                context={},
            )
            raise
