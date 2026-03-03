"""Rate limiting metrics for observability."""

from opentelemetry import metrics

# Get meter instance
meter = metrics.get_meter(__name__)

# Rate limiting counters
rate_limit_requests_total = meter.create_counter(
    name="rate_limit_requests_total",
    description="Total number of requests processed by rate limiter",
    unit="1",
)

rate_limit_exceeded_total = meter.create_counter(
    name="rate_limit_exceeded_total",
    description="Total number of requests that exceeded rate limits",
    unit="1",
)

redis_failures_total = meter.create_counter(
    name="rate_limit_redis_failures_total",
    description="Total number of Redis failures in rate limiting",
    unit="1",
)


# Token counters
tokens_consumed_total = meter.create_counter(
    name="rate_limit_tokens_consumed_total",
    description="Total tokens consumed (actual from responses)",
    unit="1",
)


def record_rate_limit_request(client_id: str, model_id: str, account_id: str, result: str):
    """Record a rate limit request."""
    rate_limit_requests_total.add(
        1,
        {
            "client_id": client_id,
            "model_id": model_id,
            "account_id": account_id,
            "result": result,  # "allowed", "exceeded", "error"
        },
    )


def record_rate_limit_exceeded(client_id: str, model_id: str, limit_type: str):
    """Record a rate limit exceeded event."""
    rate_limit_exceeded_total.add(
        1,
        {
            "client_id": client_id,
            "model_id": model_id,
            "limit_type": limit_type,  # "rpm", "tpm"
        },
    )


def record_redis_failure(operation: str, error_type: str):
    """Record a Redis failure."""
    redis_failures_total.add(
        1,
        {
            "operation": operation,  # "quota_check", "token_update", "round_robin"
            "error_type": error_type,
        },
    )


def record_tokens_consumed(client_id: str, model_id: str, tokens: int, api_type: str):
    """Record actual tokens consumed."""
    tokens_consumed_total.add(
        tokens, {"client_id": client_id, "model_id": model_id, "api_type": api_type}
    )
