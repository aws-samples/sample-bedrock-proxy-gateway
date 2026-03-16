# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Metrics collection and context management."""

from contextlib import asynccontextmanager

from observability.context_vars import client_id_context, client_name_context

# Logger will be passed from telemetry setup
logger = None


class MetricsCollector:
    """Metrics collection for business-specific metrics.

    Attributes
    ----------
        tracer: OpenTelemetry tracer instance.
        logger: Logger instance for metrics logging.
        auth_failures: Counter for authentication failures.
        model_usage: Counter for model usage tracking.
        ttft_histogram: Histogram for time-to-first-token measurements.
    """

    def __init__(self, meter, tracer, logger):
        """Initialize metrics collector.

        Args:
        ----
            meter: OpenTelemetry meter for creating metrics instruments.
            tracer: OpenTelemetry tracer for distributed tracing.
            logger: Logger instance for metrics-related logging.
        """
        self.tracer = tracer
        self.logger = logger

        # Business-specific metrics not covered by auto-instrumentation
        # Auto-instrumentation handles HTTP request metrics, but we need
        # domain-specific ones
        self.auth_failures = meter.create_counter(
            name="auth_failures_total",
            description="Authentication failures",
            unit="1",
        )

        # Track model usage for cost allocation and quota monitoring
        self.model_usage = meter.create_counter(
            name="model_usage_total",
            description="Model usage by endpoint",
            unit="1",
        )

        # Time to First Token (TTFT) is critical for streaming LLM performance
        self.ttft_histogram = meter.create_histogram(
            name="streaming_ttft_seconds",
            description="Time to first token for streaming responses",
            unit="s",
        )

        # Active requests gauge for autoscaling
        self.active_requests = meter.create_up_down_counter(
            name="active_requests",
            description="Number of currently active requests",
            unit="1",
        )

    def _get_user_attributes(self) -> dict[str, str]:
        """Get user context attributes for metrics.

        Returns
        -------
            dict: User context attributes.
        """
        attributes = {}
        client_id = client_id_context.get()
        client_name = client_name_context.get()

        if client_id:
            attributes["client.id"] = client_id
        if client_name:
            attributes["client.name"] = client_name

        return attributes

    def record_auth_failure(self, reason: str):
        """Record authentication failure.

        Args:
        ----
            reason (str): Reason for authentication failure.
        """
        attributes = {"reason": reason, **self._get_user_attributes()}
        self.auth_failures.add(1, attributes)

    @asynccontextmanager
    async def track_request(
        self,
        endpoint: str,
        model_id: str | None = None,
        method: str = "POST",  # noqa: ARG002
    ):
        """Request tracking - auto-instrumentation handles most metrics.

        Args:
        ----
            endpoint (str): API endpoint being tracked.
            model_id (Optional[str]): Model ID if applicable.
            method (str): HTTP method, defaults to "POST".

        Yields:
        ------
            None: Context manager for request tracking.
        """
        # Track business metrics with user context
        # auto-instrumentation handle technical metrics
        attributes = {"endpoint": endpoint, **self._get_user_attributes()}
        if model_id:
            attributes["model_id"] = model_id
            self.model_usage.add(1, attributes)

        # Track active requests for autoscaling
        # OTel collector exports this to CloudWatch
        self.active_requests.add(1, attributes)

        self.logger.info(
            f"Processing {endpoint} request" + (f" for model {model_id}" if model_id else "")
        )

        try:
            yield None  # Auto-instrumentation creates spans automatically
        except Exception as e:
            self.logger.error(f"{endpoint.title()} request failed: {str(e)}")
            raise
        finally:
            # Decrement active requests when done
            self.active_requests.add(-1, attributes)

    @asynccontextmanager
    async def track_stream_request(self, endpoint: str, model_id: str):
        """Stream tracking for streaming requests.

        Args:
        ----
            endpoint (str): API endpoint being tracked.
            model_id (str): Model ID for the streaming request.

        Yields:
        ------
            StreamContext: Context object with methods for tracking stream events.
        """
        attributes = {"model_id": model_id, "endpoint": endpoint, **self._get_user_attributes()}
        self.model_usage.add(1, attributes)

        # Track active requests for autoscaling (same as regular requests)
        self.active_requests.add(1, attributes)

        # Get user attributes once for the entire stream context
        user_attributes = self._get_user_attributes()

        class StreamContext:
            def __init__(self, logger, ttft_histogram, user_attrs):
                import time

                self.logger = logger
                self.ttft_histogram = ttft_histogram
                self.user_attrs = user_attrs
                self.start_time = time.time()  # Track when stream request started
                self.first_token_time = None

            def record_first_token(self):
                """Record when first token is received.

                Records the time-to-first-token metric for streaming responses.
                """
                # Only record TTFT once per stream to avoid duplicate metrics
                if self.first_token_time is None:
                    import time

                    self.first_token_time = time.time()
                    ttft = self.first_token_time - self.start_time
                    # TTFT is a key performance indicator for streaming LLMs
                    attributes = {"model_id": model_id, "endpoint": endpoint, **self.user_attrs}
                    self.ttft_histogram.record(ttft, attributes)
                    self.logger.info(
                        f"TTFT for {model_id} {ttft:.3f}s",
                        extra={"model_id": model_id, "ttft": ttft},
                    )

            def record_failure(self, error: Exception):
                """Record stream failure.

                Args:
                ----
                    error: Exception that caused the stream failure.
                """
                self.logger.error(
                    f"{endpoint.title()} stream failed for model {model_id}: {str(error)}"
                )

        try:
            yield StreamContext(self.logger, self.ttft_histogram, user_attributes)
        except Exception as e:
            self.logger.error(
                f"Failed to initialize {endpoint} stream for model {model_id}: {str(e)}"
            )
            raise
        finally:
            # Decrement active requests when stream completes
            self.active_requests.add(-1, attributes)
