# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Cache-related exceptions."""


class CacheError(Exception):
    """Base exception for cache operations."""


class CacheConnectionError(CacheError):
    """Exception raised when cache connection fails."""


class CacheOperationError(CacheError):
    """Exception raised when cache operation fails."""


class CacheConfigurationError(CacheError):
    """Exception raised when cache configuration is invalid."""
