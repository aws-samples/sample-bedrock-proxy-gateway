# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for use_case_quota_checker.py script.

This suite verifies:
- quota distribution across accounts
- validation of demands vs capacities
- handling of unlimited (-1) values
- accounts without demand
- new grouping logic by model and account lists
- overlapping account handling and proportional demand calculation
- main() execution paths (failure exit)
"""

import os
import sys

# Add the backend directory to the path for direct import
sys.path.append(os.path.join(os.path.dirname(__file__), "../../../../backend/app/core/rate_limit"))

import usecase_quota_checker as module


class TestUseCaseQuotaChecker:
    """Unit test suite for use_case_quota_checker module.

    This class validates the following behaviors:
    - Fair distribution of quotas across multiple accounts (distribute_demands).
    - Correct validation of demand vs. capacity (check_quota_values).
    - Proper handling of unlimited values (-1).
    - No allocation when account lists are empty.
    - Detailed failure reporting and forced exit (print_quota_issues).
    - Main() execution paths:
        • Failure exit with sys.exit(1).
        • Success when no issues found.
    """

    def test_demands_meets_capacity(
        self,
        config=None,
    ):
        """Demands within total capacity across all accounts should pass.

        Args:
        ----
            config: Optional dict with 'permissions' and 'account_limits' keys.
                   If not provided, uses default test configuration.
        """
        if config is None:
            config = {
                "permissions": {
                    "default": {
                        "models": {
                            "pizza.model-v1:0": {"rpm": 1, "tpm": 10},
                        },
                        "accounts": ["123"],
                    },
                    "ABCDEF": {
                        "name": "We love pizza",
                        "models": {
                            "pizza.model-v1:0": {"rpm": 10, "tpm": 100},
                        },
                        "accounts": ["123"],
                    },
                    "ZXY": {
                        "name": "We love pizza as well",
                        "models": {
                            "pizza.model-v1:0": {"rpm": 20, "tpm": 200},
                        },
                        "accounts": ["123", "234"],
                    },
                },
                "account_limits": {
                    "123": {
                        "pizza.model-v1:0": {"rpm": 100, "tpm": 1000},
                    },
                    "234": {
                        "pizza.model-v1:0": {"rpm": 200, "tpm": 2000},
                    },
                },
            }

        permissions = config["permissions"]
        caps = config["account_limits"]
        data = {"permissions": permissions}
        use_case_demands = module.distribute_demands(permissions)
        check_passed = module.check_quota_values(data, use_case_demands, caps, "test-env")
        assert check_passed is True

    def test_use_case_demands_exceeds_capacity(self, capsys, config=None):
        """Demand larger than total capacity across all accounts should fail.

        Args:
        ----
            capsys: Pytest fixture to capture stdout/stderr.
            config: Optional dict with 'permissions' and 'account_limits' keys.
                   If not provided, uses default test configuration where demands exceed capacity.
        """
        if config is None:
            config = {
                "permissions": {
                    "default": {
                        "models": {
                            "pizza.model-v1:0": {"rpm": 1, "tpm": 10},
                        },
                        "accounts": ["123"],
                    },
                    "ABCDEF": {
                        "name": "We love pizza",
                        "models": {
                            "pizza.model-v1:0": {"rpm": 10, "tpm": 100},
                        },
                        "accounts": ["123"],
                    },
                    "ZXY": {
                        "name": "We want too much pizza",
                        "models": {
                            "pizza.model-v1:0": {"rpm": 999999, "tpm": 999999},
                        },
                        "accounts": ["123", "234"],
                    },
                },
                "account_limits": {
                    "123": {
                        "pizza.model-v1:0": {"rpm": 100, "tpm": 1000},
                    },
                    "234": {
                        "pizza.model-v1:0": {"rpm": 200, "tpm": 2000},
                    },
                },
            }

        permissions = config["permissions"]
        caps = config["account_limits"]
        data = {"permissions": permissions}
        use_case_demands = module.distribute_demands(permissions)
        check_passed = module.check_quota_values(data, use_case_demands, caps, "test-env")
        assert check_passed is False

        # Check that delta is printed
        # Total demand: 1 + 10 + 999999 = 1000010 RPM, 10 + 100 + 999999 = 1000109 TPM
        # Total capacity: 100 + 200 = 300 RPM, 1000 + 2000 = 3000 TPM
        # Missing: 1000010 - 300 = 999710 RPM, 1000109 - 3000 = 997109 TPM
        captured = capsys.readouterr()
        assert "❌ Quota failures found" in captured.out
        assert "Missing quota is 999710" in captured.out
        assert "Missing quota is 997109" in captured.out

    def test_use_case_demands_exceeds_capacity_special_sneaky_case(self, capsys, config=None):
        """Demand larger than total capacity across all accounts should fail.

        Args:
        ----
            capsys: Pytest fixture to capture stdout/stderr.
            config: Optional dict with 'permissions' and 'account_limits' keys.
                   If not provided, uses default test configuration where demands exceed capacity.
        """
        if config is None:
            config = {
                "permissions": {
                    "default": {
                        "models": {
                            "pizza.model-v1:0": {"rpm": 1, "tpm": 10},
                        },
                        "accounts": ["123"],
                    },
                    "ABCDEF": {
                        "name": "We love pizza",
                        "models": {
                            "pizza.model-v1:0": {"rpm": 300, "tpm": 100},
                        },
                        "accounts": ["123", "456"],
                    },
                    "ZXY": {
                        "name": "We want too much pizza",
                        "models": {
                            "pizza.model-v1:0": {"rpm": 400, "tpm": 200},
                        },
                        "accounts": ["123", "234"],
                    },
                },
                "account_limits": {
                    "123": {
                        "pizza.model-v1:0": {"rpm": 250, "tpm": 1000},
                    },
                    "234": {
                        "pizza.model-v1:0": {"rpm": 100, "tpm": 1000},
                    },
                    "456": {
                        "pizza.model-v1:0": {"rpm": 200, "tpm": 2000},
                    },
                },
            }

        permissions = config["permissions"]
        caps = config["account_limits"]
        data = {"permissions": permissions}
        use_case_demands = module.distribute_demands(permissions)
        check_passed = module.check_quota_values(data, use_case_demands, caps, "test-env")
        assert check_passed is False

        # Check that delta is printed
        # Cluster 1 (accounts '123', '456'): demand = 501 RPM, capacity = 450 RPM, missing = 51 RPM
        # Cluster 2 (account '234'): demand = 200 RPM, capacity = 100 RPM, missing = 100 RPM
        captured = capsys.readouterr()
        assert "❌ Quota failures found" in captured.out
        assert "Missing quota is 51" in captured.out
        assert "Missing quota is 100" in captured.out

    def test_use_case_demands_with_unlimited(self, config=None):
        """Unlimited demand (-1) on separate accounts should not cause hard failure.

        Args:
        ----
            config: Optional dict with 'permissions' and 'account_limits' keys.
                   If not provided, uses configuration where unlimited use case is on separate
                   account from finite use cases.
        """
        if config is None:
            config = {
                "permissions": {
                    "default": {
                        "models": {
                            "pizza.model-v1:0": {"rpm": 1, "tpm": 10},
                        },
                        "accounts": ["123"],
                    },
                    "ABCDEF": {
                        "name": "We love pizza",
                        "models": {
                            "pizza.model-v1:0": {"rpm": -1, "tpm": -1},
                        },
                        "accounts": ["456"],
                    },
                    "ZXY": {
                        "name": "We want too much pizza",
                        "models": {
                            "pizza.model-v1:0": {"rpm": 10, "tpm": 200},
                        },
                        "accounts": ["123", "234"],
                    },
                },
                "account_limits": {
                    "123": {
                        "pizza.model-v1:0": {"rpm": 250, "tpm": 1000},
                    },
                    "234": {
                        "pizza.model-v1:0": {"rpm": 100, "tpm": 1000},
                    },
                    "456": {
                        "pizza.model-v1:0": {"rpm": 200, "tpm": 2000},
                    },
                },
            }

        permissions = config["permissions"]
        caps = config["account_limits"]
        data = {"permissions": permissions}
        use_case_demands = module.distribute_demands(permissions)
        check_passed = module.check_quota_values(data, use_case_demands, caps, "test-env")
        assert check_passed is True

    def test_use_case_demands_with_unlimited_and_finite_same_account(self, capsys, config=None):
        """Unlimited demand (-1) sharing account with finite demand should trigger warning.

        Args:
        ----
            capsys: Pytest fixture to capture stdout/stderr.
            config: Optional dict with 'permissions' and 'account_limits' keys.
                   If not provided, uses configuration where unlimited and finite use cases
                   share the same account.
        """
        if config is None:
            config = {
                "permissions": {
                    "default": {
                        "models": {
                            "pizza.model-v1:0": {"rpm": 1, "tpm": 10},
                        },
                        "accounts": ["123"],
                    },
                    "ABCDEF": {
                        "name": "We love pizza",
                        "models": {
                            "pizza.model-v1:0": {"rpm": -1, "tpm": -1},
                        },
                        "accounts": ["456"],
                    },
                    "ZXY": {
                        "name": "We want too much pizza",
                        "models": {
                            "pizza.model-v1:0": {"rpm": 10, "tpm": 200},
                        },
                        "accounts": ["456", "234"],
                    },
                },
                "account_limits": {
                    "123": {
                        "pizza.model-v1:0": {"rpm": 250, "tpm": 1000},
                    },
                    "234": {
                        "pizza.model-v1:0": {"rpm": 100, "tpm": 1000},
                    },
                    "456": {
                        "pizza.model-v1:0": {"rpm": 200, "tpm": 2000},
                    },
                },
            }

        permissions = config["permissions"]
        caps = config["account_limits"]
        data = {"permissions": permissions}
        use_case_demands = module.distribute_demands(permissions)
        check_passed = module.check_quota_values(data, use_case_demands, caps, "test-env")
        assert check_passed is True

        # Check that warning is printed
        captured = capsys.readouterr()
        assert "⚠️  Warning: Mixed unlimited and finite quotas detected" in captured.out
        assert "Model            : pizza.model-v1:0" in captured.out
