# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Context variables for user context in logs and traces."""

import hashlib
from contextvars import ContextVar

# Context variables to store user info across async calls
client_id_context: ContextVar[str] = ContextVar("client_id", default="")
client_name_context: ContextVar[str] = ContextVar("client_name", default="")
scope_context: ContextVar[str] = ContextVar("scope", default="")


def _hash_pii(value: str) -> str:
    """Hash PII values consistently for observability.

    Args:
    ----
        value: The PII value to hash.

    Returns:
    -------
        str: SHA256 hash of the value.
    """
    return hashlib.sha256(value.encode()).hexdigest()[:16]


def set_user_context(
    client_id: str,
    client_name: str | None = None,
    scope: str | None = None,
):
    """Set user context for current async task.

    Args:
    ----
        client_id: Client identifier from JWT token (unique M2M client ID).
        client_name: Client name to store in context.
        scope: OAuth scope from JWT token.
    """
    client_id_context.set(client_id)
    if client_name:
        client_name_context.set(client_name)
    if scope:
        scope_context.set(scope)


def clear_user_context():
    """Clear user context.

    Removes user and client identifiers from the current async context.
    Should be called after request processing to prevent context leakage.
    """
    client_id_context.set(None)
    client_name_context.set(None)
    scope_context.set(None)
