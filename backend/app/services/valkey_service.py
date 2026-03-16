# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Valkey connection service using valkey-glide with IAM authentication."""

from urllib.parse import urlparse

from config import config
from glide import (
    GlideClusterClient,
    GlideClusterClientConfiguration,
    IamAuthConfig,
    NodeAddress,
    ServerCredentials,
    ServiceType,
)

_client = None


async def create_valkey_client() -> GlideClusterClient:
    """Create Valkey client with IAM authentication support.

    Returns
    -------
        Configured GlideClusterClient with IAM auth or password auth
    """
    global _client

    if _client is not None:
        return _client

    # Parse connection URL
    parsed = urlparse(config.valkey_url)
    host = parsed.hostname or "localhost"
    port = parsed.port or 6379

    addresses = [NodeAddress(host, port)]

    # Configure credentials
    credentials = None
    if (
        config.elasticache_use_iam
        and config.elasticache_cluster_name
        and config.elasticache_username
    ):
        # Use IAM authentication with auto-refresh
        iam_config = IamAuthConfig(
            cluster_name=config.elasticache_cluster_name,
            service=ServiceType.ELASTICACHE,
            region=config.aws_region,
            refresh_interval_seconds=300,  # Refresh every 5 minutes
        )
        credentials = ServerCredentials(
            username=config.elasticache_username,
            iam_config=iam_config,
        )
    elif parsed.password:
        # Use password authentication
        credentials = ServerCredentials(
            username=parsed.username or "default",
            password=parsed.password,
        )

    # Create client configuration
    client_config = GlideClusterClientConfiguration(
        addresses=addresses,
        use_tls=config.valkey_ssl,
        credentials=credentials,
        request_timeout=5000,  # 5 seconds
    )

    _client = await GlideClusterClient.create(client_config)
    return _client


async def close_valkey_client():
    """Close the global Valkey client."""
    global _client
    if _client is not None:
        await _client.close()
        _client = None
