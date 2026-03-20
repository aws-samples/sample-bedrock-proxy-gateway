# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Cache modules for rate limiting and credential caching."""

from .memory_cache import get_cache, set_cache

__all__ = [
    "get_cache",
    "set_cache",
]
