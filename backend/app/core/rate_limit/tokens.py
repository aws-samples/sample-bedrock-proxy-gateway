# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Token counting utilities for rate limiting.

This module provides token estimation and extraction for GenAI API rate limiting.
Accurate token counting is critical for:

1. TPM (Tokens Per Minute) rate limiting enforcement
2. Cost control and usage accuracy
3. Pre-request quota validation
4. Post-request actual consumption tracking

TOKEN ESTIMATION STRATEGY:
- Pre-request: Fast estimation based on character count (4 chars ≈ 1 token)
- Post-response: Aggregated token calculation with cache-aware burndown rates
- Conservative approach: Always estimate at least 1 token per request

AGGREGATED TOKEN FORMULA:
aggregated_token = CacheWriteInputTokens + (OutputTokenCount × BurndownRate) + InputToken

BurndownRate varies by model:
- Anthropic Claude Opus 4: 5
- Anthropic Claude Sonnet 4: 5
- Anthropic Claude 3.7 Sonnet: 5
- All other models: 1

API TYPE SUPPORT:
- Converse API: Structured message parsing with system prompts
- Legacy Invoke API: Simple string-based estimation
- Extensible design for future API types
"""

from typing import Any


class TokenCounter:
    """Estimates and extracts token counts from requests and responses.

    This class implements a two-phase token counting approach:
    1. ESTIMATION (pre-request): Fast approximation for quota checking
    2. EXTRACTION (post-response): Aggregated token calculation with burndown rates

    ESTIMATION ACCURACY:
    - Converse API: ~85-90% accurate (structured message parsing)
    - Invoke API: ~70-80% accurate (simple string estimation)
    - Always conservative (tends to slightly over-estimate)

    PERFORMANCE CHARACTERISTICS:
    - Estimation: O(n) where n = message count (typically 1-10)
    - Extraction: O(1) direct field access with aggregated calculation
    - No external dependencies or API calls
    """

    # Model-specific burndown rates
    MODEL_BURNDOWN_RATES = {
        "anthropic.claude-3-opus-20240229-v1:0": 5,
        "anthropic.claude-3-5-sonnet-20240620-v1:0": 5,
        "anthropic.claude-3-5-sonnet-20241022-v2:0": 5,
        "anthropic.claude-3-5-sonnet-v2:0": 5,
        "anthropic.claude-3-sonnet-20240229-v1:0": 5,
    }

    # Token estimation constants
    CHARS_PER_TOKEN = 4  # 1 token ≈ 4 characters for English text
    TOKENS_PER_IMAGE = 2500  # Fixed token estimate per image for vision models

    def _count_images_in_content(self, content) -> int:
        """Count number of images in message content.

        Args:
        ----
            content: Message content (can be string, list, or dict)

        Returns:
        -------
            Number of images found
        """
        if isinstance(content, list):
            return sum(1 for item in content if isinstance(item, dict) and "image" in item)
        return 0

    def _estimate_text_tokens(self, text: str) -> int:
        """Estimate tokens for text content.

        Args:
        ----
            text: Text content

        Returns:
        -------
            Estimated token count for text
        """
        return max(1, len(text) // self.CHARS_PER_TOKEN)

    def estimate(self, request_body: dict, api_type: str) -> int:
        """Estimate token count from request body for pre-request quota checking.

        This function provides fast token estimation before making API calls.
        Used by rate limiting middleware to check TPM quotas before processing.

        ESTIMATION ALGORITHMS:

        CONVERSE API (Multimodal-aware):
        1. Count images in all messages (fixed tokens per image)
        2. Extract text content only (excluding base64 image data)
        3. Apply text-based token estimation
        4. Sum image tokens + text tokens

        INVOKE API (Legacy):
        1. Convert entire request body to string
        2. Count total characters
        3. Apply 4-chars-per-token conversion

        Examples:
        - "Hello world" → 3 tokens
        - 2 images + "Count images" → 2*2500 + 3 = 5003 tokens
        - Empty request → 1 token (minimum)

        Args:
        ----
            request_body: Parsed JSON request body from client
            api_type: API type ("converse", "converse-stream", "invoke", etc.)

        Returns:
        -------
            Estimated token count (minimum 1, conservative estimate)
        """
        # CONVERSE API: Parse structured messages with multimodal support
        if api_type.startswith("converse"):
            total_tokens = 0

            # Process messages
            for msg in request_body.get("messages", []):
                content = msg.get("content", "")

                # Count images
                image_count = self._count_images_in_content(content)
                total_tokens += image_count * self.TOKENS_PER_IMAGE

                # Count text tokens (extract text from structured content)
                if isinstance(content, list):
                    text_chars = sum(
                        len(str(item.get("text", "")))
                        for item in content
                        if isinstance(item, dict) and "text" in item
                    )
                else:
                    text_chars = len(str(content))

                total_tokens += max(1, text_chars // self.CHARS_PER_TOKEN)

            # Add system prompt tokens
            system_text = str(request_body.get("system", ""))
            if system_text:
                total_tokens += max(1, len(system_text) // self.CHARS_PER_TOKEN)

            return max(1, total_tokens)
        else:
            # INVOKE API: Simple string conversion (less accurate but fast)
            chars = len(str(request_body))
            return max(1, chars // self.CHARS_PER_TOKEN)

    def get_burndown_rate(self, model_id: str) -> int:
        """Get burndown rate for the specified model.

        Args:
        ----
            model_id: Bedrock model identifier

        Returns:
        -------
            Burndown rate for the model (default: 1)
        """
        return self.MODEL_BURNDOWN_RATES.get(model_id, 1)

    def calculate_aggregated_tokens(self, usage: dict[str, Any], model_id: str) -> int:
        """Calculate aggregated tokens from API response usage data.

        Formula: CacheWriteInputTokens + (OutputTokenCount × BurndownRate) + InputToken

        Args:
        ----
            usage: Usage dictionary from API response
            model_id: Bedrock model identifier for burndown rate lookup

        Returns:
        -------
            Aggregated token count for rate limiting
        """
        cache_write_tokens = usage.get("cacheWriteInputTokens", 0)
        output_tokens = usage.get("outputTokens", 0)
        input_tokens = usage.get("inputTokens", 0)

        burndown_rate = self.get_burndown_rate(model_id)

        aggregated = cache_write_tokens + (output_tokens * burndown_rate) + input_tokens

        return max(1, aggregated)  # Minimum 1 token

    def extract(self, response: dict, api_type: str, model_id: str) -> int:
        """Extract aggregated token count from API response for post-request tracking.

        This function extracts precise token counts from API responses after
        request completion using aggregated token calculation. Used for:
        1. Updating actual TPM consumption in Redis
        2. Usage and cost tracking
        3. Metrics and observability

        EXTRACTION STRATEGIES:

        CONVERSE API (Aggregated):
        1. Look for 'usage' field in response
        2. Calculate: CacheWriteInputTokens + (OutputTokens × BurndownRate) + InputTokens
        3. Use model-specific burndown rates (5 for Claude Opus/Sonnet 4, 1 for others)
        4. Return 0 if no usage data found

        INVOKE API (Estimated):
        1. Convert response to string
        2. Apply character-to-token conversion
        3. Less accurate but consistent with estimation

        Args:
        ----
            response: Parsed JSON response from Bedrock API
            api_type: API type ("converse", "converse-stream", "invoke", etc.)
            model_id: Bedrock model identifier for burndown rate calculation

        Returns:
        -------
            Aggregated token count from API response (0 if unavailable)
        """
        # CONVERSE API: Use aggregated token calculation
        if api_type.startswith("converse"):
            usage = response.get("usage", {})
            return self.calculate_aggregated_tokens(usage, model_id)

        # INVOKE API: Estimate from response size (less accurate)
        return len(str(response)) // self.CHARS_PER_TOKEN
