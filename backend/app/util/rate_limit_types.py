# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Rate limit types and enums."""

from enum import Enum


class RateLimitReason(str, Enum):
    """Rate limit exceeded reason."""

    RPM = "rpm"
    TPM = "tpm"
    ACCOUNT_RPM = "account_rpm"
    ACCOUNT_TPM = "account_tpm"


class RateLimitScope(str, Enum):
    """Rate limit scope level."""

    CLIENT = "client"
    ACCOUNT = "account"
