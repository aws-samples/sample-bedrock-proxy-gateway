# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Load-test Bedrock converse API with Locust.

Usage:
    locust -f locust.py --users 1 --spawn-rate 10 --run-time 30s --headless --tags gateway --only-summary
    locust -f locust.py --users 16 --spawn-rate 10 --run-time 3m --headless --tags gateway

"""

import os
import time
from datetime import datetime, timedelta

import boto3
import requests
from botocore import UNSIGNED
from botocore.config import Config
from locust import User, events, tag, task

RESULT_FOLDER = f"./tmp_results/{datetime.now().strftime('%m__%d___%H__%M__%S')}"
SLOW_TRACE_FILE = f"{RESULT_FOLDER}/slow_traces_results.csv"
SLOW_TRACE_THRESHOLD_VALUE_IN_MS = 2000
INFRA_STATS_FILE = f"{RESULT_FOLDER}/infra_stats.csv"
TEST_METADATA_FILE = f"{RESULT_FOLDER}/test_metadata.txt"


AWS_REGION = "us-east-1"
ENVIRONMENT_CONFIG = {
    "urls": {
        "dev": "https://dev-alb.example.net",
        "test": "https://test-alb.example.net",
        "prod": "https://prod-alb.example.net",
    },
    "ecs": {
        "dev": "ecs-np-app1234-dev-bedrock-proxy-gateway",
        "test": "ecs-np-app1234-test-bedrock-proxy-gateway",
        "prod": "ecs-app1234-prod-bedrock-proxy-gateway",
    },
}
ENVIRONMENT = "dev"
API_URL = ENVIRONMENT_CONFIG["urls"][ENVIRONMENT]
CLOUDWATCH_ECS_CLUSTER = ENVIRONMENT_CONFIG["ecs"][ENVIRONMENT]

BEDROCK_MODEL_ID_LIST = [
    # "cohere.embed-english-v3",
    # "cohere.embed-multilingual-v3",
    # "us.deepseek.r1-v1:0",
    # "meta.llama3-70b-instruct-v1:0",
    # "us.meta.llama3-1-70b-instruct-v1:0",
    "us.meta.llama3-1-8b-instruct-v1:0",
    # "us.meta.llama3-3-70b-instruct-v1:0",
    # "meta.llama3-8b-instruct-v1:0",
    # "us.mistral.pixtral-large-2502-v1:0",
    # "mistral.mistral-large-2402-v1:0",
    # "mistral.mixtral-8x7b-instruct-v0:1",
    "us.amazon.nova-micro-v1:0",
    "us.amazon.nova-lite-v1:0",
    # "us.amazon.nova-pro-v1:0",
    # "us.anthropic.claude-3-haiku-20240307-v1:0",
    # "us.anthropic.claude-3-5-haiku-20241022-v1:0",
    # "us.anthropic.claude-3-sonnet-20240229-v1:0",
    # "us.anthropic.claude-3-5-sonnet-20240620-v1:0",
    # "us.anthropic.claude-3-5-sonnet-20241022-v2:0",
    # "us.anthropic.claude-3-7-sonnet-20250219-v1:0",
    # "us.anthropic.claude-sonnet-4-20250514-v1:0",
    # "amazon.titan-embed-image-v1",
    # "amazon.titan-embed-text-v1",
    # "amazon.titan-embed-text-v2:0",
]

PROMPT = "how are you? tell me a story about Juventus"

CLOUDWATCH_QUERY_WAIT_TIME = 60  # Maximum wait time in seconds


# Global counter for successful invocations
successful_invocations = 0
# Dynamic counters based on BEDROCK_MODEL_ID_LIST
successful_invocations_by_model = dict.fromkeys(BEDROCK_MODEL_ID_LIST, 0)

# Global test timing variables
test_start_datetime = None
test_end_datetime = None

# Create header in CSV file if it doesn't exist
os.makedirs(RESULT_FOLDER, exist_ok=True)
with open(SLOW_TRACE_FILE, "w") as f:
    f.write("trace_id,e2e_ms,bedrock_ms,platform_overhead_ms\n")

# Initialize test metadata file
with open(TEST_METADATA_FILE, "w") as f:
    f.write("=== Load Test Metadata ===\n")
    f.write(f"Test Start Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    f.write("Token Expiration: (will be updated when first token is generated)\n")
    f.write("Test Finish Time: (will be updated when test completes)\n")
    f.write("Total Successful Invocations: (will be updated when test completes)\n")
    # Dynamically write successful invocations line for each model
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

    # Update the metadata file with finish time and successful invocations
    try:
        with open(TEST_METADATA_FILE) as f:
            content = f.read()

        # Replace the finish time line
        content = content.replace(
            "Test Finish Time: (will be updated when test completes)",
            f"Test Finish Time: {test_finish_time}",
        )

        # Replace the successful invocations line
        content = content.replace(
            "Total Successful Invocations: (will be updated when test completes)",
            f"Total Successful Invocations: {successful_invocations}",
        )
        # Dynamically replace successful invocations for each model
        for model_id in BEDROCK_MODEL_ID_LIST:
            content = content.replace(
                f"Total Successful Invocations for {model_id}: (will be updated when test completes)",
                f"Total Successful Invocations for {model_id}: {successful_invocations_by_model[model_id]}",
            )

        with open(TEST_METADATA_FILE, "w") as f:
            f.write(content)
    except Exception as e:
        print(f"Error updating test metadata file: {e}")

    # gather_infra_stats()


def gather_infra_stats():
    """Gather infrastructure statistics during the test."""
    # Query CloudWatch for ECS container insights
    print("⏳ Waiting 5 minutes to let CloudWatch collect the metrics...")
    time.sleep(300)
    print("✅ Waiting completed!!!")

    print("📈 Querying CloudWatch for infrastructure metrics...")
    try:
        cloudwatch_logs = boto3.client("logs", region_name=AWS_REGION)

        # Convert datetime objects to epoch timestamps for CloudWatch
        start_time = int(test_start_datetime.timestamp())
        end_time = int(test_end_datetime.timestamp())

        # CloudWatch Insights query for ECS container metrics
        query = f"""
        fields @timestamp, ClusterName, ContainerCpuUtilization, ContainerMemoryUtilization
        | filter ClusterName = "{CLOUDWATCH_ECS_CLUSTER}"
        | stats max(ContainerCpuUtilization) as MaxCpuUtilization,
                avg(ContainerCpuUtilization) as AvgCpuUtilization,
                max(ContainerMemoryUtilization) as MaxMemoryUtilization,
                avg(ContainerMemoryUtilization) as AvgMemoryUtilization
        """
        # Start the query
        response = cloudwatch_logs.start_query(
            logGroupName=f"/aws/ecs/containerinsights/{CLOUDWATCH_ECS_CLUSTER}/performance",
            startTime=start_time,
            endTime=end_time,
            queryString=query,
        )

        query_id = response["queryId"]

        # Wait for query to complete
        wait_time = 0

        while wait_time < CLOUDWATCH_QUERY_WAIT_TIME:
            result = cloudwatch_logs.get_query_results(queryId=query_id)
            if result["status"] == "Complete":
                break
            time.sleep(2)
            wait_time += 2

        # Process results and save to CSV
        if result["status"] == "Complete" and result["results"]:
            # First (and only) row of aggregated results
            stats = result["results"][0]

            # Create infra stats CSV
            with open(INFRA_STATS_FILE, "w") as f:
                f.write("metric,value\n")
                for field in stats:
                    field_name = field["field"]
                    field_value = field["value"]
                    f.write(f"{field_name},{field_value}\n")

                # Add test duration
                test_duration = (test_end_datetime - test_start_datetime).total_seconds()
                f.write(f"test_duration_seconds,{test_duration}\n")

            # Print summary
            for field in stats:
                field_name = field["field"]
                field_value = field["value"]
                print(f"📊 {field_name}: {field_value}")

        else:
            print("⚠️ CloudWatch query did not return results or timed out")
            # Create empty CSV with headers
            with open(INFRA_STATS_FILE, "w") as f:
                f.write("metric,value\n")
                f.write("MaxCpuUtilization,N/A\n")
                f.write("AvgCpuUtilization,N/A\n")
                f.write("MaxMemoryUtilization,N/A\n")
                f.write("AvgMemoryUtilization,N/A\n")
                test_duration = (test_end_datetime - test_start_datetime).total_seconds()
                f.write(f"test_duration_seconds,{test_duration}\n")

    except Exception as e:
        print(f"⚠️ Error querying CloudWatch: {e}")
        # Create error CSV
        try:
            with open(INFRA_STATS_FILE, "w") as f:
                f.write("metric,value\n")
                f.write("error,CloudWatch query failed\n")
                if test_start_datetime and test_end_datetime:
                    test_duration = (test_end_datetime - test_start_datetime).total_seconds()
                    f.write(f"test_duration_seconds,{test_duration}\n")
        except Exception as csv_error:
            print(f"Error creating error CSV: {csv_error}")


# Register event handlers
events.test_start.add_listener(on_test_start)
events.test_stop.add_listener(on_test_stop)


class BedrockUser(User):
    """Simulates a Locust user that sends inference requests to the Bedrock API.

    This is the class that defines the Locust user
    """

    def generate_token(self):
        """Generate an access token from OAuth2 endpoint.

        Returns
        -------
            str: Bearer token string for Authorization header.
        """
        # Get OAuth configuration from environment
        oauth_token_url = os.getenv("OAUTH_TOKEN_ENDPOINT", "")
        client_id = os.getenv("OAUTH_CLIENT_ID", "")
        client_secret = os.getenv("OAUTH_CLIENT_SECRET", "")

        if not all([oauth_token_url, client_id, client_secret]):
            raise ValueError(
                "OAuth configuration missing. Set OAUTH_TOKEN_ENDPOINT, OAUTH_CLIENT_ID, OAUTH_CLIENT_SECRET"
            )

        # Setup mTLS certificates if available
        cert_path = os.getenv("MTLS_CERT_PATH")
        key_path = os.getenv("MTLS_KEY_PATH")
        if cert_path and key_path:
            self.CERT_PATH_CONFIG = (cert_path, key_path)
        else:
            self.CERT_PATH_CONFIG = None

        payload = {
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "client_credentials",
        }

        # Add scope if configured
        scope = os.getenv("OAUTH_SCOPE")
        if scope:
            payload["scope"] = scope

        response = requests.post(oauth_token_url, data=payload, cert=self.CERT_PATH_CONFIG)
        response.raise_for_status()
        token_data = response.json()
        token = token_data["access_token"]

        expires_in = token_data.get("expires_in", 3600)
        self.token_expires_at = datetime.now() + timedelta(seconds=expires_in)

        # Update the metadata file with token expiration info
        try:
            with open(TEST_METADATA_FILE) as f:
                content = f.read()

            token_info = f"Token Expiration: {self.token_expires_at.strftime('%Y-%m-%d %H:%M:%S')} (expires in {expires_in}s)"
            content = content.replace(
                "Token Expiration: (will be updated when first token is generated)",
                token_info,
            )

            with open(TEST_METADATA_FILE, "w") as f:
                f.write(content)
        except Exception as e:
            print(f"Error updating test metadata file with token info: {e}")

        return f"Bearer {token}"

    def is_token_expired(self):
        """Check if the current token is expired or about to expire.

        Returns
        -------
            bool: True if token is expired or will expire within 60 seconds
        """
        if not hasattr(self, "token_expires_at"):
            return True

        now = datetime.now()
        time_until_expiry = (self.token_expires_at - now).total_seconds()

        if time_until_expiry <= 0:
            print(f"⚠️  TOKEN EXPIRED at {self.token_expires_at.strftime('%Y-%m-%d %H:%M:%S')}")
            return True
        elif time_until_expiry <= 60:
            print(
                f"⚠️  TOKEN EXPIRES SOON in {int(time_until_expiry)} seconds at {self.token_expires_at.strftime('%Y-%m-%d %H:%M:%S')}"
            )
            return False

        return False

    def create_bedrock_clients(self, token):
        """Create a Bedrock runtime client with the provided auth token.

        Args:
        ----
            token (str): Bearer token for API authorization.

        Returns:
        -------
            boto3.client: Configured Bedrock runtime client.
        """
        bedrock = boto3.client(
            "bedrock-runtime",
            region_name=AWS_REGION,
            endpoint_url=API_URL,
            config=(
                # Config(signature_version=UNSIGNED)
                # if ENVIRONMENT == "feature"
                # else Config(signature_version=UNSIGNED, client_cert=self.CERT_PATH_CONFIG)
                Config(signature_version=UNSIGNED, client_cert=self.CERT_PATH_CONFIG)
            ),
        )

        def add_api_token(request, **kwargs):  # noqa: ARG001 **kwargs is needed here, cannot be omitted
            request.headers.add_header("Authorization", token)
            return request

        bedrock.meta.events.register("before-sign.bedrock-runtime.*", add_api_token)

        direct_bedrock = boto3.client(
            "bedrock-runtime",
            region_name=AWS_REGION,
        )
        return bedrock, direct_bedrock

    def on_start(self):
        """Initialize the user session by authenticating and creating the Bedrock client.

        Executed only once per user and BEFORE the response time are calculated
        """
        # Generate token
        TOKEN = self.generate_token()
        self.MODEL_ITERATOR = 0

        # Create Bedrock client
        self.bedrock, self.direct_bedrock = self.create_bedrock_clients(TOKEN)

    # --------------------------------------------------------------------------

    @tag("gateway")
    @task
    def converse_gateway(self) -> None:
        """Send a prompt to the Bedrock API and record both Bedrock and e2e latencies with sub-millisecond precision.

        Locust user task
        """
        # Add these global declarations at the beginning
        global successful_invocations, successful_invocations_by_model

        model_id_list = BEDROCK_MODEL_ID_LIST

        e2e_start_time = time.perf_counter_ns()

        try:
            # ──  Bedrock call  ────────────────────────────────────────────────
            # print(f"Calling model {model_id_list[self.MODEL_ITERATOR]}")
            resp = self.bedrock.converse(
                modelId=model_id_list[self.MODEL_ITERATOR],
                messages=[{"role": "user", "content": [{"text": PROMPT}]}],
                inferenceConfig={"maxTokens": 256},
            )

            e2e_end_time = time.perf_counter_ns()

            # Convert to **float** milliseconds for accuracy
            e2e_response_time_in_ms = (e2e_end_time - e2e_start_time) / 1_000_000.0
            bedrock_response_time_ms = float(resp.get("metrics", {}).get("latencyMs", 0.0))

            gateway_overhead_response_time_in_ms = (
                e2e_response_time_in_ms - bedrock_response_time_ms
            )

            # Increment successful invocations counter
            successful_invocations += 1

            # Dynamically increment counter for the current model
            current_model = model_id_list[self.MODEL_ITERATOR]
            successful_invocations_by_model[current_model] += 1

            self.MODEL_ITERATOR += 1
            if len(model_id_list) <= self.MODEL_ITERATOR:
                self.MODEL_ITERATOR = 0

            # ── Persist slow traces, if any  ─────────────────────────────────
            if gateway_overhead_response_time_in_ms >= SLOW_TRACE_THRESHOLD_VALUE_IN_MS:
                trace_id = (
                    resp.get("ResponseMetadata", {})
                    .get("HTTPHeaders", {})
                    .get("x-trace-id", "none")
                )
                # print(
                #     f"Slow trace >{SLOW_TRACE_THRESHOLD_VALUE_IN_MS} ms : "
                #     f"Bedrock {bedrock_response_time_ms:.1f} ms  |  "
                #     f"E2E {e2e_response_time_in_ms:.1f} ms  |  "
                #     f"Platform {gateway_overhead_response_time_in_ms:.1f} ms  ==> {trace_id}"
                # )
                # print("\n")
                with open(SLOW_TRACE_FILE, "a", encoding="utf-8") as f:
                    f.write(
                        f"{trace_id},{e2e_response_time_in_ms},{bedrock_response_time_ms},{gateway_overhead_response_time_in_ms:.3f}\n"
                    )

            # events.request.fire(
            #     request_type="load",
            #     name="converse_e2e",
            #     response_time=int(e2e_response_time_in_ms),
            #     response_length=0,
            #     exception=None,
            #     context={},
            # )
            # events.request.fire(
            #     request_type="load",
            #     name="bedrock_only",
            #     response_time=int(bedrock_response_time_ms),
            #     response_length=0,
            #     exception=None,
            #     context={},
            # )
            events.request.fire(
                request_type="load",
                name="gateway_overhead",
                response_time=int(gateway_overhead_response_time_in_ms),
                response_length=0,
                exception=None,
                context={},
            )

        except Exception as exc:
            # Check if this is a 403 error and stop the test if so
            if "403" in str(exc) or "Forbidden" in str(exc):
                print(f"🛑 CRITICAL: 403 Forbidden error detected - {exc}")
                print("🛑 Stopping test due to authentication failure...")

                # Update metadata file with error info
                try:
                    with open(TEST_METADATA_FILE, "a") as f:
                        f.write(
                            f"\n🛑 TEST STOPPED DUE TO 403 ERROR at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                        )
                        f.write(f"Error: {exc}\n")
                except Exception:
                    pass

                # Stop the test
                self.environment.runner.quit()
                return

            # Record failures so they appear in the CSV
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

    @tag("direct")
    @task
    def direct_bedrock(self) -> None:
        """Send a prompt to the Bedrock API and record both Bedrock and e2e latencies with sub-millisecond precision.

        Locust user task
        """
        global successful_invocations

        model_id_list = BEDROCK_MODEL_ID_LIST
        e2e_start_time = time.perf_counter_ns()

        try:
            resp = self.direct_bedrock.converse(
                modelId=model_id_list[self.MODEL_ITERATOR],
                messages=[{"role": "user", "content": [{"text": PROMPT}]}],
                inferenceConfig={"maxTokens": 256},
            )
            # If the response object has headers, print them

            # print(f"Direct Bedrock response headers: {resp.headers}")

            bedrock_response_time_in_ms = int(resp["metrics"]["latencyMs"])
            e2e_end_time = time.perf_counter_ns()

            # Convert to **float** milliseconds for accuracy
            e2e_response_time_in_ms = int((e2e_end_time - e2e_start_time) / 1_000_000.0)
            direct_bedrock_response_time_ms = e2e_response_time_in_ms - bedrock_response_time_in_ms

            # Increment successful invocations counter
            successful_invocations += 1

            events.request.fire(
                request_type="load",
                name="direct_bedrock",
                response_time=direct_bedrock_response_time_ms,
                response_length=len(resp["output"]["message"]["content"][0]["text"]),
                exception=None,
                context={},
            )

        except Exception as exc:
            # Check if this is a 403 error and stop the test if so
            if "403" in str(exc) or "Forbidden" in str(exc):
                print(f"🛑 CRITICAL: 403 Forbidden error detected - {exc}")
                print("🛑 Stopping test due to authentication failure...")

                # Update metadata file with error info
                try:
                    with open(TEST_METADATA_FILE, "a") as f:
                        f.write(
                            f"\n🛑 TEST STOPPED DUE TO 403 ERROR at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                        )
                        f.write(f"Error: {exc}\n")
                except Exception as e:
                    print(f"Failed to update test metadata file: {e}")
                    pass

                # Stop the test
                self.environment.runner.quit()
                return

            # Record failures so they appear in the CSV
            # print(f"Error: {exc}")
            error_type = "generic"
            error_name = "error"
            if "429" in str(exc) or "Forbidden" in str(exc):
                error_type = "throttling"
                error_name = "429"

            events.request.fire(
                request_type=error_type,
                name=error_name,
                response_time=int((time.perf_counter_ns() - e2e_start_time) / 1_000_000.0),
                response_length=0,
                exception=exc,
                context={},
            )
            raise
