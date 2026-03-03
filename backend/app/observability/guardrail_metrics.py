"""Guardrail metrics for observability."""

from opentelemetry import metrics

# Get meter instance
meter = metrics.get_meter(__name__)


guardrail_applied_total = meter.create_counter(
    name="guardrail_applied_total",
    description="Total number of requests with guardrails applied",
    unit="1",
)

guardrail_not_found_total = meter.create_counter(
    name="guardrail_not_found_total",
    description="Total number of requests with guardrail not found errors",
    unit="1",
)


def record_guardrail_applied(client_id: str, logical_id: str, account_id: str, api_type: str):
    """Record a guardrail applied event."""
    guardrail_applied_total.add(
        1,
        {
            "client_id": client_id,
            "logical_id": logical_id,
            "account_id": account_id,
            "api_type": api_type,  # "invoke", "converse", "apply"
        },
    )


def record_guardrail_not_found(client_id: str, logical_id: str, account_id: str):
    """Record a guardrail not found event."""
    guardrail_not_found_total.add(
        1,
        {
            "client_id": client_id,
            "logical_id": logical_id,
            "account_id": account_id,
        },
    )
