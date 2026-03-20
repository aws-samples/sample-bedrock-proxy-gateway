# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

#!/usr/bin/env python3
"""Integration tests for all Bedrock models and APIs - Restructured."""

import asyncio
import io
import json
import logging
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import boto3
import numpy as np
from bedrock_client import BedrockProxyGateway
from dotenv import load_dotenv
from PIL import Image

# Configure logging for mixed events
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler(f"test_logs_{int(time.time())}.log")],
)
logger = logging.getLogger(__name__)

# Get repo root (4 levels up from test/integration/python/main.py)
REPO_ROOT = Path(__file__).parent.parent.parent.parent

# Load environment-specific .env file from repo root (same as notebooks)
ENVIRONMENT = os.getenv("ENVIRONMENT", "dev")
env_file = REPO_ROOT / f".env.{ENVIRONMENT}"
load_dotenv(env_file)

# Load configuration from test/integration/
config_path = Path(__file__).parent.parent / "config.json"
with open(config_path) as f:
    config = json.load(f)

# Configuration from .env file
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
API_URL = os.getenv("GATEWAY_API_URL", "https://your-gateway-url.com")
SECRET_ID = os.getenv("GATEWAY_SECRET_ID", "bedrock-gateway-dev-oauth-credentials")

# Fetch credentials from Secrets Manager (same pattern as notebooks)
_session = boto3.Session(profile_name=os.getenv("AWS_PROFILE"), region_name=AWS_REGION)
_secret = json.loads(
    _session.client("secretsmanager").get_secret_value(SecretId=SECRET_ID)["SecretString"]
)
CLIENT_ID = _secret["client_id"]
CLIENT_SECRET = _secret["client_secret"]
AUTH_URL = _secret["token_url"]
AUDIENCE = _secret.get("audience", "")
INFERENCE_MODELS = config["models"]["python"]["inference"]
EMBEDDING_MODELS = config["models"]["python"]["embedding"]
MULTI_MODALS = config["models"]["python"]["multi_modal"]
REASONING_MODELS = config["models"]["python"]["reasoning"]
VISION_LLMS = config["model_capabilities"]["image_vision"]
PROMPT_CACHING_LLMS = config["model_capabilities"]["prompt_caching"]
FRAMEWORK_LIBS = ["langchain", "langgraph", "strands", "litellm"]

# Optional mTLS certificate paths
MTLS_CERT_PATH = os.getenv("MTLS_CERT_PATH")
MTLS_KEY_PATH = os.getenv("MTLS_KEY_PATH")


class BedrockTester:
    """Integration test suite for Bedrock Gateway APIs - Restructured."""

    def __init__(self):
        """Initialize Bedrock tester with authentication manager."""
        self.bedrock_gateway = BedrockProxyGateway(
            client_id=CLIENT_ID,
            client_secret=CLIENT_SECRET,
            mtls_cert_path=MTLS_CERT_PATH,
            mtls_key_path=MTLS_KEY_PATH,
            region="us-east-1",
            bedrock_runtime_endpoint_url=API_URL,
            oauth_token_url=AUTH_URL,
            audience=AUDIENCE,
        )
        self.bedrock_client = self.bedrock_gateway.get_bedrock_client()

    def test_connectivity(self) -> tuple[bool, str]:
        """Test gateway connectivity and token acquisition.

        Returns
        -------
            Tuple[bool, str]: Success status and error message if any.
        """
        try:
            import requests

            # Verify token acquisition works
            token = self.bedrock_gateway.get_token()
            if not token:
                return False, "Failed to acquire OAuth token"

            # Verify gateway is reachable
            response = requests.get(f"{API_URL}/health", verify=False)
            if response.status_code != 200:
                return False, f"Health check failed: HTTP {response.status_code}"

            return True, "SUCCESS"
        except Exception as e:
            return False, str(e)

    # Core API Tests
    def test_bedrock_converse(self, model_id: str) -> tuple[bool, str]:
        """Test Bedrock converse API."""
        try:
            messages = [{"role": "user", "content": [{"text": "Hello, respond with just 'Hi'"}]}]
            self.bedrock_client.converse(modelId=model_id, messages=messages)
            return True, "SUCCESS"
        except Exception as e:
            return False, str(e)

    def test_bedrock_converse_stream(self, model_id: str) -> tuple[bool, str]:
        """Test Bedrock converse stream API."""
        try:
            messages = [{"role": "user", "content": [{"text": "Count to 3"}]}]
            response = self.bedrock_client.converse_stream(modelId=model_id, messages=messages)
            stream = response.get("stream")
            if stream:
                for event in stream:
                    if "contentBlockDelta" in event:
                        pass
            return True, "SUCCESS"
        except Exception as e:
            return False, str(e)

    def test_bedrock_prompt_caching(self, model_id: str) -> tuple[bool, str]:
        """Test Bedrock prompt caching API."""
        target_token_nr = 1200

        char_per_token = 4
        # Use deterministic prompt with model_id to ensure consistency
        np.random.seed(hash(model_id) % 2**32)
        short_prompt = "".join(np.random.choice(list("abcdefghijklmnopqrstuvwxyz"), size=12)) + "!"
        nr_repeat = int(target_token_nr / (len(short_prompt) / char_per_token))
        long_prompt = nr_repeat * short_prompt

        def _get_cache_read_write(bedrock_response: dict) -> (int, int):
            cache_read = bedrock_response["usage"]["cacheReadInputTokens"]
            cache_write = bedrock_response["usage"]["cacheWriteInputTokens"]
            return cache_read, cache_write

        try:
            messages = [
                {
                    "role": "user",
                    "content": [
                        {"text": long_prompt},
                        {"cachePoint": {"type": "default"}},
                    ],
                },
                {
                    "role": "user",
                    "content": [
                        {"text": "Which sentence did I just repeat many times and how often?"},
                    ],
                },
            ]

            response_init = self.bedrock_client.converse(modelId=model_id, messages=messages)
            cache_read_init, cache_write_init = _get_cache_read_write(response_init)

            if cache_read_init or not cache_write_init:
                return False, "Caching not working. Not initialized correctly."

            # Add delay to allow cache propagation
            time.sleep(2)

            response_repeat = self.bedrock_client.converse(modelId=model_id, messages=messages)
            cache_read_repeat, _ = _get_cache_read_write(response_repeat)

            if not cache_read_repeat:
                return False, "Caching not working. Not reusing correctly."

            return True, "SUCCESS"
        except Exception as e:
            return False, str(e)

    def test_bedrock_invoke(self, model_id: str) -> tuple[bool, str]:
        """Test Bedrock invoke model API."""
        try:
            if "anthropic" in model_id:
                body = {
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": 100,
                    "messages": [{"role": "user", "content": "Hello"}],
                }
            elif "nova" in model_id:
                body = {
                    "messages": [{"role": "user", "content": [{"text": "Hello"}]}],
                    "inferenceConfig": {"max_new_tokens": 100},
                }
            elif "llama" in model_id:
                body = {"prompt": "Hello", "max_gen_len": 100, "temperature": 0.1}
            elif "mistral" in model_id:
                body = {"prompt": "Hello", "max_tokens": 100, "temperature": 0.1}
            else:
                body = {"prompt": "Hello", "max_tokens": 100}

            response = self.bedrock_client.invoke_model(modelId=model_id, body=json.dumps(body))
            json.loads(response["body"].read())
            return True, "SUCCESS"
        except Exception as e:
            return False, str(e)

    def test_bedrock_invoke_stream(self, model_id: str) -> tuple[bool, str]:
        """Test Bedrock invoke model with response stream API."""
        try:
            if "anthropic" in model_id:
                body = {
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": 100,
                    "messages": [{"role": "user", "content": "Count to 3"}],
                }
            elif "nova" in model_id:
                body = {
                    "messages": [{"role": "user", "content": [{"text": "Count to 3"}]}],
                    "inferenceConfig": {"max_new_tokens": 100},
                }
            elif "llama" in model_id:
                body = {"prompt": "Count to 3", "max_gen_len": 100, "temperature": 0.1}
            elif "mistral" in model_id:
                body = {"prompt": "Count to 3", "max_tokens": 100, "temperature": 0.1}
            else:
                body = {"prompt": "Count to 3", "max_tokens": 100}

            response = self.bedrock_client.invoke_model_with_response_stream(
                modelId=model_id, body=json.dumps(body)
            )
            for event in response["body"]:
                json.loads(event["chunk"]["bytes"])
            return True, "SUCCESS"
        except Exception as e:
            return False, str(e)

    # Advanced Feature Tests
    def _generate_image_with_size(self, target_mb: float) -> bytes:
        """Generate an image with approximately the target size in MB.

        Args:
        ----
            target_mb: Target image size in MB.

        Returns:
        -------
            bytes: Image data as bytes.
        """
        target_bytes = int(target_mb * 1024 * 1024)

        # Start with base dimensions and adjust
        width = height = 100

        # Estimate dimensions needed for target size
        # PNG compression varies, so we'll iterate to get close
        for _ in range(10):
            img = Image.new("RGB", (width, height), color="lightblue")
            pixels = np.array(img)

            # Add some visual content (red circle)
            center_x, center_y = width // 2, height // 2
            y, x = np.ogrid[:height, :width]
            radius = min(width, height) // 4
            mask = (x - center_x) ** 2 + (y - center_y) ** 2 <= radius**2
            pixels[mask] = [255, 100, 100]

            # Add noise for less compression
            noise = np.random.randint(0, 50, (height, width, 3))
            pixels = np.clip(pixels.astype(int) + noise, 0, 255).astype(np.uint8)

            img = Image.fromarray(pixels)
            buffer = io.BytesIO()
            img.save(buffer, format="PNG", optimize=False)
            current_size = len(buffer.getvalue())

            if abs(current_size - target_bytes) < target_bytes * 0.1:  # Within 10%
                break

            # Adjust dimensions based on size difference
            scale_factor = (target_bytes / current_size) ** 0.5
            width = int(width * scale_factor)
            height = int(height * scale_factor)
            width = max(50, min(width, 4000))  # Reasonable bounds
            height = max(50, min(height, 4000))

        image_bytes = buffer.getvalue()
        actual_size_mb = len(image_bytes) / (1024 * 1024)
        logger.info(
            f"Image size: {actual_size_mb:.2f} MB ({actual_size_mb / target_mb * 100:.0f}% of target)"
        )
        return image_bytes

    def test_image_vision(
        self, model_id: str, target_mb: float = 0.1, nr_images: int = 1
    ) -> tuple[bool, str]:
        """Test multimodal capabilities.

        Args:
        ----
            model_id: The model to test.
            target_mb: Target image size in MB (default: 0.1 MB).
            nr_images: Number of images with the specified size
        """
        try:
            if model_id not in VISION_LLMS:
                return False, f"Image search not supported for {model_id}"

            image_bytes = self._generate_image_with_size(target_mb)

            content = [
                {
                    "text": "How many images do you see? Respond with the a numeric integer value only (e.g. 1, 2, 3)"
                }
            ]

            content.extend(
                nr_images * [{"image": {"format": "png", "source": {"bytes": image_bytes}}}]
            )

            response = self.bedrock_client.converse(
                modelId=model_id,
                messages=[{"role": "user", "content": content}],
            )
            result = int(response["output"]["message"]["content"][0]["text"])

            # NOTE: The following validation adds some uncertainty to the test induced by the randomness in LLM inference.
            # This could be reduced by using structured output. It's not used here to mix tests of different capabilities.
            # Most SOTA vision models should be able to provide reliable output at this level without structured output though.
            if result == nr_images:
                return True, "SUCCESS"
            else:
                return False, "Could not identify number of images correctly"
        except Exception as e:
            return False, str(e)

    # Test Categories
    def test_reasoning(self, model_id: str) -> dict:
        """Test inference model with core APIs and advanced features."""
        logger.info(
            f"🧠 Starting reasoning tests: {model_id}. This might take several minutes per model."
        )
        result = {"model_id": model_id, "type": "reasoning"}

        # Core APIs
        logger.info(f"Testing extended thinking for {model_id}")
        success, error = self.test_extended_thinking(model_id)
        result["converse"] = {"success": success, "error": error}
        logger.info(f"Converse result: {'✅ PASS' if success else '❌ FAIL'} - {error}")
        time.sleep(3)

        logger.info(f"✅ Completed reasoning model test: {model_id}")
        return result

    def test_extended_thinking(self, model_id: str) -> tuple[bool, str]:
        """Test extended thinking by Claude."""
        try:
            human_message = "Who has better food? Italy or France? Think deeply about your response. If you get it right you get 1 Mio USD. Reason for as long as possible."
            logger.debug(f"Human message: {human_message}")

            start_time = datetime.now(UTC)
            messages = [{"role": "user", "content": [{"text": human_message}]}]
            response = self.bedrock_client.converse(
                modelId=model_id,
                messages=messages,
                inferenceConfig={"maxTokens": 25000},
                additionalModelRequestFields={
                    "reasoning_config": {"type": "enabled", "budget_tokens": 20000},
                },
            )
            reasoning_time = datetime.now(UTC) - start_time
            content = response["output"]["message"]["content"]

            reasoning_text = content[0]["reasoningContent"]["reasoningText"]["text"]
            final_response = content[1]["text"]

            logger.debug(f"Reasoning text: {reasoning_text}")
            logger.debug(f"Final Response: {final_response}")
            logger.debug(f"Reasoning time: {reasoning_time}")

            if reasoning_text:
                return True, "SUCCESS"
            else:
                return False, "No reasoning text in response"

        except Exception as e:
            return False, str(e)

    def test_embedding(self, model_id: str) -> tuple[bool, str]:
        """Test embedding model capabilities."""
        try:
            if "embed" not in model_id.lower() and "titan" not in model_id.lower():
                return False, "Not an embedding model"

            if "cohere" in model_id.lower():
                payload = {"texts": ["Test embedding"], "input_type": "search_document"}
            elif "titan" in model_id.lower():
                payload = {"inputText": "Test embedding"}
            else:
                payload = {"inputText": "Test embedding", "dimensions": 256}

            response = self.bedrock_client.invoke_model(modelId=model_id, body=json.dumps(payload))
            result = json.loads(response["body"].read())
            if "embedding" in result or "embeddings" in result:
                return True, "SUCCESS"
            return False, "No embedding in response"
        except Exception as e:
            return False, str(e)

    # Framework Integration Tests
    def test_langchain_integration(self, model_id: str) -> tuple[bool, str]:
        """Test Langchain integration."""
        try:
            from langchain_aws import ChatBedrock

            chat = ChatBedrock(
                model_id=model_id, client=self.bedrock_client, model_kwargs={"max_tokens": 50}
            )
            chat.invoke("Hello")
            return True, "SUCCESS"
        except Exception as e:
            return False, str(e)

    def test_langgraph_integration(self, model_id: str) -> tuple[bool, str]:
        """Test Langgraph integration."""
        try:
            from typing import TypedDict

            from langchain_aws import ChatBedrock
            from langgraph.graph import END, StateGraph

            class State(TypedDict):
                message: str

            def chat_node(state: State) -> State:
                chat = ChatBedrock(
                    model_id=model_id, client=self.bedrock_client, model_kwargs={"max_tokens": 50}
                )
                response = chat.invoke(state["message"])
                return {"message": str(response.content)}

            graph = StateGraph(State)
            graph.add_node("chat", chat_node)
            graph.set_entry_point("chat")
            graph.add_edge("chat", END)
            app = graph.compile()
            app.invoke({"message": "Hello"})
            return True, "SUCCESS"
        except Exception as e:
            return False, str(e)

    def test_strands_integration(self, model_id: str) -> tuple[bool, str]:
        """Test Strands integration."""
        try:
            from strands import Agent
            from strands.models import BedrockModel

            bedrock_model = BedrockModel(model_id=model_id)
            bedrock_model.client = self.bedrock_gateway.get_bedrock_client()
            agent = Agent(model=bedrock_model)
            agent("Say hello")
            return True, "SUCCESS"
        except Exception as e:
            return False, str(e)

    def test_litellm_integration(self, model_id: str) -> tuple[bool, str]:
        """Test LiteLLM integration."""
        try:
            import litellm

            bedrock = self.bedrock_gateway.get_bedrock_client(dummy_aws_creds=True)
            litellm.completion(
                model=f"bedrock/{model_id}",
                messages=[{"role": "user", "content": "Hello"}],
                max_tokens=50,
                aws_bedrock_client=bedrock,
            )
            return True, "SUCCESS"
        except Exception as e:
            return False, str(e)

    # Test Categories
    def test_inference_model(self, model_id: str) -> dict:
        """Test inference model with core APIs and advanced features."""
        logger.info(f"🚀 Starting inference model test: {model_id}")
        result = {"model_id": model_id, "type": "inference"}

        # Core APIs
        logger.info(f"Testing converse API for {model_id}")
        success, error = self.test_bedrock_converse(model_id)
        result["converse"] = {"success": success, "error": error}
        logger.info(f"Converse result: {'✅ PASS' if success else '❌ FAIL'} - {error}")
        time.sleep(3)

        logger.info(f"Testing converse stream API for {model_id}")
        success, error = self.test_bedrock_converse_stream(model_id)
        result["converse_stream"] = {"success": success, "error": error}
        logger.info(f"Converse stream result: {'✅ PASS' if success else '❌ FAIL'} - {error}")
        time.sleep(3)

        logger.info(f"Testing invoke API for {model_id}")
        success, error = self.test_bedrock_invoke(model_id)
        result["invoke"] = {"success": success, "error": error}
        logger.info(f"Invoke result: {'✅ PASS' if success else '❌ FAIL'} - {error}")
        time.sleep(3)

        logger.info(f"Testing invoke stream API for {model_id}")
        success, error = self.test_bedrock_invoke_stream(model_id)
        result["invoke_stream"] = {"success": success, "error": error}
        logger.info(f"Invoke stream result: {'✅ PASS' if success else '❌ FAIL'} - {error}")
        time.sleep(3)

        if model_id in PROMPT_CACHING_LLMS:
            logger.info(f"Testing prompt caching for {model_id}.")
            success, error = self.test_bedrock_prompt_caching(model_id)
            result["prompt_caching"] = {"success": success, "error": error}
            logger.info(f"Prompt caching: {'✅ PASS' if success else '❌ FAIL'} - {error}")
            time.sleep(3)

        logger.info(f"✅ Completed inference model test: {model_id}")
        return result

    def test_embedding_model_full(self, model_id: str) -> dict:
        """Test embedding model capabilities."""
        logger.info(f"🚀 Starting embedding model test: {model_id}")
        result = {"model_id": model_id, "type": "embedding"}

        logger.info(f"Testing embedding API for {model_id}")
        success, error = self.test_embedding(model_id)
        result["embedding"] = {"success": success, "error": error}
        logger.info(f"Embedding result: {'✅ PASS' if success else '❌ FAIL'} - {error}")
        time.sleep(3)

        logger.info(f"✅ Completed embedding model test: {model_id}")
        return result

    def test_framework_integration_full(self, model_id: str, framework: str) -> dict:
        """Test framework integration with a model."""
        logger.info(f"🚀 Starting framework test: {framework} with {model_id}")
        result = {"model_id": model_id, "framework": framework, "type": "framework"}

        logger.info(f"Testing {framework} integration")
        if framework == "langchain":
            success, error = self.test_langchain_integration(model_id)
        elif framework == "langgraph":
            success, error = self.test_langgraph_integration(model_id)
        elif framework == "strands":
            success, error = self.test_strands_integration(model_id)
        elif framework == "litellm":
            success, error = self.test_litellm_integration(model_id)
        else:
            success, error = False, f"Unknown framework: {framework}"

        result[framework] = {"success": success, "error": error}
        logger.info(f"{framework} result: {'✅ PASS' if success else '❌ FAIL'} - {error}")
        time.sleep(3)

        logger.info(f"✅ Completed framework test: {framework}")
        return result

    def test_multi_modal(self, model_id: str) -> dict:
        """Test multi-modal capabilities including image vision if supported."""
        logger.info(f"🚀 Starting multi-modal test: {model_id}")
        result = {"model_id": model_id, "type": "multi_modal"}

        # Test image search only if model supports it
        if model_id in VISION_LLMS:
            logger.info(f"Testing image vision for {model_id}")
            mb_size = 0.1
            nr_images = 2
            logger.info(f"Testing with {nr_images} images of ~ {mb_size} MB.")
            success, error = self.test_image_vision(
                model_id, target_mb=mb_size, nr_images=nr_images
            )
            result["image_vision"] = {"success": success, "error": error}
            logger.info(f"Image vision result: {'✅ PASS' if success else '❌ FAIL'} - {error}")
        else:
            logger.info(f"Image vision result: ⏭️ SKIP - Not supported for {model_id}")
        time.sleep(3)

        logger.info(f"✅ Completed multi-modal test: {model_id}")
        return result

    async def run_all_tests(self) -> list[dict]:
        """Run all test categories."""
        all_results = []

        # Test inference models
        for model_id in INFERENCE_MODELS:
            result = self.test_inference_model(model_id)
            all_results.append(result)

        # Test reasoning
        for model_id in REASONING_MODELS:
            result = self.test_reasoning(model_id)
            all_results.append(result)

        # Test embedding models
        for model_id in EMBEDDING_MODELS:
            result = self.test_embedding_model_full(model_id)
            all_results.append(result)

        # Test multi-modals
        for model_id in MULTI_MODALS:
            result = self.test_multi_modal(model_id)
            all_results.append(result)

        # Test framework integrations (use first inference model)
        test_model = INFERENCE_MODELS[0] if INFERENCE_MODELS else None
        if test_model:
            for framework in FRAMEWORK_LIBS:
                result = self.test_framework_integration_full(test_model, framework)
                all_results.append(result)

        return all_results

    def print_consolidated_results(self, results: list[dict]):
        """Print consolidated test results in a single table."""
        print("\n" + "=" * 120)
        print("🐍 CONSOLIDATED INTEGRATION TEST RESULTS")
        print("=" * 120)

        # Header
        print(f"{'Model/Framework':<40} {'Type':<12} {'Test':<20} {'Status':<10} {'Error':<30}")
        print("-" * 120)

        for result in results:
            model_id = result.get("model_id", "")
            test_type = result.get("type", "")
            framework = result.get("framework", "")

            # Display name
            if test_type == "framework":
                display_name = f"{framework} ({model_id[:20]}...)"
            else:
                display_name = model_id

            # Get all test results (excluding metadata)
            test_results = {
                k: v
                for k, v in result.items()
                if k not in ["model_id", "type", "framework"] and isinstance(v, dict)
            }

            for test_name, test_result in test_results.items():
                status = "✅ PASS" if test_result.get("success") else "❌ FAIL"
                error = test_result.get("error", "")[:30]
                print(
                    f"{display_name:<40} {test_type:<12} {test_name:<20} {status:<10} {error:<30}"
                )

        # Summary
        total_tests = sum(
            len(
                [
                    k
                    for k, v in result.items()
                    if k not in ["model_id", "type", "framework"] and isinstance(v, dict)
                ]
            )
            for result in results
        )
        passed_tests = sum(
            sum(
                1
                for k, v in result.items()
                if k not in ["model_id", "type", "framework"]
                and isinstance(v, dict)
                and v.get("success")
            )
            for result in results
        )

        print("-" * 120)
        print(
            f"📊 Total Tests: {total_tests} | ✅ Passed: {passed_tests} | ❌ Failed: {total_tests - passed_tests}"
        )
        print(
            f"📈 Success Rate: {(passed_tests / total_tests * 100):.1f}%"
            if total_tests > 0
            else "📈 Success Rate: 0%"
        )
        print("=" * 120)

        return total_tests - passed_tests


async def main():
    """Run all integration tests."""
    tester = BedrockTester()

    # Test onboarding endpoint first
    print("Testing gateway connectivity...")
    success, error = tester.test_connectivity()
    if success:
        print("✅ Connectivity test passed")
    else:
        print(f"❌ Connectivity test failed: {error}")
        exit(1)

    logger.info("🚀 Starting Bedrock Gateway Integration Tests")
    logger.info(f"📋 Inference Models: {len(INFERENCE_MODELS)}")
    logger.info(f"📋 Embedding Models: {len(EMBEDDING_MODELS)}")
    logger.info(f"📋 Models tested for Multi-modality: {len(MULTI_MODALS)}")
    logger.info(f"🖼️ Models with image vision tested: {len(VISION_LLMS)}")
    logger.info(f"🧠 Models tested for reasoning: {len(REASONING_MODELS)}")
    logger.info(f"📋 Framework Libraries tested: {len(FRAMEWORK_LIBS)}")

    logger.info("🔄 Running all test categories with 3-second intervals...")
    results = await tester.run_all_tests()
    failed_count = tester.print_consolidated_results(results)

    if failed_count:
        logger.info("❌ Not all tests passed.")
    else:
        logger.info("✅ All tests passed!")

    if failed_count > 0:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
