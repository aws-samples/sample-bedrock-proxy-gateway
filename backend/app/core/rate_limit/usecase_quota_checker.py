# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Quota distribution and validation tool.

This script processes quota YAML files for dev and test environments from
backend/app/core/rate_limit/config directory. It distributes requested RPM/TPM
quotas across accounts, compares them against account capacities, and produces
a validation summary.

Algorithm:
1. For each request in "permissions", distribute quotas fairly across accounts:
   - Even split across accounts.
   - Remainder distributed one by one.
   - A value of -1 means unlimited demand (always marked as FAIL).
2. Compare distributed demands with "account_limits".
3. Produce a quota validation report:
   - RPM/TPM demand vs. capacity.
   - Status ("OK" or "FAIL").
   - Warnings for mixed unlimited and limited quotas.

Output:
- Console summary per account and model.
- Detailed warnings and failures for quota violations.
- Exit with code 1 if any blocking failures are detected.

Example:
    Run the validation for both dev and test:

        python tables_check_automation.py
"""

import argparse
import json
import logging
import os
import sys
from collections import defaultdict

import yaml

# === Configuration directory and environment files ===
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_DIR = os.path.join(CURRENT_DIR, "config")

# === Logger setup ===
logger = logging.getLogger(__name__)
LOCAL_LOG_LEVEL = "INFO"

# Structure mapping environment names to their config file paths
ENVIRONMENT_FILES = [
    {
        "env_name": "test",
        "file_path": os.path.join(CONFIG_DIR, "test.yaml"),
    },
    {
        "env_name": "dev",
        "file_path": os.path.join(CONFIG_DIR, "dev.yaml"),
    },
]


def distribute_demands(permissions):
    """Distribute RPM/TPM demands across accounts for each use case.

    Args:
        permissions: dict of use case permissions

    Returns:
        dict: {use_case_name: {model_name: demand_info}}
    """
    use_case_demands = {}

    for use_case_key, use_case_info in permissions.items():
        models = use_case_info.get("models", {})
        accounts = use_case_info.get("accounts", [])

        if not accounts:
            continue

        use_case_demands[use_case_key] = {}

        for model_name, quotas in models.items():
            rpm = quotas.get("rpm", 0)
            tpm = quotas.get("tpm", 0)
            unlimited = rpm == -1 or tpm == -1

            if unlimited:
                use_case_demands[use_case_key][model_name] = {
                    "rpm": 0,
                    "tpm": 0,
                    "unlimited": True,
                    "accounts": accounts,
                }
            else:
                use_case_demands[use_case_key][model_name] = {
                    "rpm": rpm,
                    "tpm": tpm,
                    "unlimited": False,
                    "accounts": accounts,
                }

    return use_case_demands


def _group_use_cases_by_model_and_accounts(use_case_demands):
    """Group use cases by model first, then by account list for checking.

    Returns:
        dict: {model_name: {account_group_key: [(use_case_name, demand_info)]}}
        where account_group_key is a sorted tuple of accounts for consistent grouping
    """
    model_to_account_groups = defaultdict(lambda: defaultdict(list))

    for use_case_name, use_case_info in use_case_demands.items():
        for model_name, demand_info in use_case_info.items():
            # Create account group key (sorted tuple for consistent grouping)
            account_list = demand_info["accounts"]
            account_group_key = tuple(sorted(account_list))

            # Store original demand info
            model_to_account_groups[model_name][account_group_key].append(
                (use_case_name, demand_info)
            )

    return model_to_account_groups


def _create_clusters_with_subset_handling(account_groups):
    """Create clusters and handle subset relationships.

    Algorithm:
    1. Create initial clusters from account groups
    2. If cluster X is a subset of cluster Y:
       - Move overlapping accounts from X to Y
       - Add proportional demand to Y (based on moved accounts)
       - Adjust X demand to reflect remaining accounts
       - Remove X if empty

    Args:
        account_groups: dict of {account_group_key: [(use_case_name, demand_info)]}

    Returns:
        dict: {cluster_key: [(use_case_name, demand_info, adjusted_demand_info)]}
    """
    # Step 1: Create initial clusters
    clusters = {}
    for group_key, use_cases in account_groups.items():
        cluster_key = tuple(sorted(group_key))
        clusters[cluster_key] = []

        for use_case_name, demand_info in use_cases:
            # Create adjusted demand (initially same as original)
            adjusted_demand = {
                "rpm": demand_info["rpm"],
                "tpm": demand_info["tpm"],
                "unlimited": demand_info["unlimited"],
                "accounts": list(demand_info["accounts"]),
            }
            clusters[cluster_key].append((use_case_name, demand_info, adjusted_demand))

    # Step 2: Handle subset relationships
    clusters = _handle_subset_relationships(clusters)

    return clusters


def _handle_subset_relationships(clusters):
    """Handle subset relationships between clusters.

    Args:
        clusters: dict of {cluster_key: [(use_case_name, demand_info, adjusted_demand_info)]}

    Returns:
        dict: Updated clusters after handling subset relationships
    """
    result = {}
    processed_clusters = set()

    # Sort clusters by size (largest first) to handle subsets properly
    sorted_clusters = sorted(clusters.items(), key=lambda x: len(x[0]), reverse=True)

    for cluster_key, use_cases in sorted_clusters:
        if cluster_key in processed_clusters:
            continue

        cluster_accounts = set(cluster_key)
        result[cluster_key] = list(use_cases)
        processed_clusters.add(cluster_key)

        # Find clusters that have overlapping accounts with this cluster
        for other_key, other_use_cases in sorted_clusters:
            if other_key in processed_clusters or other_key == cluster_key:
                continue

            other_accounts = set(other_key)

            # Check if clusters have overlapping accounts
            overlapping_accounts = cluster_accounts.intersection(other_accounts)
            if overlapping_accounts:
                # Move overlapping accounts and adjust demands
                result = _merge_overlapping_cluster(
                    result, cluster_key, other_use_cases, overlapping_accounts
                )
                processed_clusters.add(other_key)

    return result


def _merge_overlapping_cluster(result, main_cluster_key, other_use_cases, overlapping_accounts):
    """Merge an overlapping cluster into the main cluster.

    Args:
        result: Current cluster result
        main_cluster_key: Key of the main cluster
        other_cluster_key: Key of the other cluster
        other_use_cases: Use cases in the other cluster
        overlapping_accounts: Set of overlapping accounts

    Returns:
        dict: Updated result with merged clusters
    """
    # Process each use case in the other cluster
    for use_case_name, original_demand, _ in other_use_cases:
        use_case_accounts = set(original_demand["accounts"])

        # Calculate accounts that overlap with main cluster
        accounts_in_main = use_case_accounts.intersection(overlapping_accounts)
        accounts_remaining = use_case_accounts - overlapping_accounts

        if accounts_in_main:
            # Calculate proportional demand for the main cluster
            proportion_main = len(accounts_in_main) / len(use_case_accounts)
            main_demand = {
                "rpm": int(original_demand["rpm"] * proportion_main),
                "tpm": int(original_demand["tpm"] * proportion_main),
                "unlimited": original_demand["unlimited"],
                "accounts": list(accounts_in_main),
            }

            # Add to main cluster
            result[main_cluster_key].append((use_case_name, original_demand, main_demand))

        if accounts_remaining:
            # Calculate proportional demand for remaining accounts
            proportion_remaining = len(accounts_remaining) / len(use_case_accounts)
            remaining_demand = {
                "rpm": int(original_demand["rpm"] * proportion_remaining),
                "tpm": int(original_demand["tpm"] * proportion_remaining),
                "unlimited": original_demand["unlimited"],
                "accounts": list(accounts_remaining),
            }

            # Create new cluster for remaining accounts
            remaining_key = tuple(sorted(accounts_remaining))
            if remaining_key not in result:
                result[remaining_key] = []
            result[remaining_key].append((use_case_name, original_demand, remaining_demand))

    return result


def _find_overlapping_account_groups(account_groups):
    """Find groups that have overlapping accounts and merge them into clusters.

    Args:
        account_groups: dict of {account_group_key: [(use_case_name, demand_info)]}

    Returns:
        dict: {cluster_key: [(use_case_name, demand_info, adjusted_demand_info)]}
    """
    return _create_clusters_with_subset_handling(account_groups)


def _calculate_usecases_model_demands(use_cases, use_case_key_to_display_name):
    """Calculate total demands and build use case info list for a model.

    Args:
        use_cases: List of (use_case_name, demand_info, adjusted_demand_info) tuples
        use_case_key_to_display_name: Mapping from use case key to display name

    Returns:
        tuple: (total_rpm, total_tpm, use_case_info_list)
    """
    total_rpm = 0
    total_tpm = 0
    use_case_info_list = []

    for use_case_name, _, adjusted_demand_info in use_cases:
        if adjusted_demand_info["unlimited"]:
            use_case_info_list.append(
                {
                    "name": use_case_key_to_display_name.get(use_case_name, use_case_name),
                    "id": use_case_name,
                    "rpm": "unlimited",
                    "tpm": "unlimited",
                }
            )
        else:
            total_rpm += adjusted_demand_info["rpm"]
            total_tpm += adjusted_demand_info["tpm"]
            use_case_info_list.append(
                {
                    "name": use_case_key_to_display_name.get(use_case_name, use_case_name),
                    "id": use_case_name,
                    "rpm": adjusted_demand_info["rpm"],
                    "tpm": adjusted_demand_info["tpm"],
                }
            )

    return total_rpm, total_tpm, use_case_info_list


def _calculate_model_capacity(use_cases, model_name, capacities, cluster_accounts=None):
    """Calculate total capacity for a model based on use cases.

    Args:
        use_cases: List of (use_case_name, demand_info, adjusted_demand_info) tuples
        model_name: Name of the model
        capacities: Account capacities
        cluster_accounts: Set of accounts in this specific cluster (if None, uses all accounts from use cases)

    Returns:
        tuple: (total_rpm_capacity, total_tpm_capacity)
    """
    total_rpm_capacity = 0
    total_tpm_capacity = 0

    # Use cluster_accounts if provided, otherwise get all unique accounts from use cases
    if cluster_accounts is not None:
        accounts_to_check = cluster_accounts
    else:
        # Get all unique accounts from all use cases in this cluster
        all_accounts = set()
        for _, demand_info, _ in use_cases:
            all_accounts.update(demand_info["accounts"])
        accounts_to_check = all_accounts

    for account in accounts_to_check:
        if account in capacities:
            account_capacity = capacities[account]
            if model_name in account_capacity:
                model_capacity = account_capacity[model_name]
                total_rpm_capacity += model_capacity.get("rpm", 0)
                total_tpm_capacity += model_capacity.get("tpm", 0)

    return total_rpm_capacity, total_tpm_capacity


def _print_cluster_debug_info(
    adjusted_groups, model_name, use_case_key_to_display_name, capacities
):
    """Print debug information for all clusters in a model.

    Args:
        adjusted_groups: Dictionary of clusters
        model_name: Name of the model
        use_case_key_to_display_name: Mapping from use case key to display name
        capacities: Account capacities
    """
    logger.debug(f"\nCLUSTERS CREATED FOR {model_name}:")

    for i, (cluster_key, use_cases) in enumerate(adjusted_groups.items(), 1):
        cluster_rpm, cluster_tpm, use_case_info_list = _calculate_usecases_model_demands(
            use_cases, use_case_key_to_display_name
        )

        # Calculate capacity for this cluster
        cluster_rpm_capacity, cluster_tpm_capacity = _calculate_model_capacity(
            use_cases, model_name, capacities, set(cluster_key)
        )

        logger.debug(f"Cluster {i}: {cluster_key}")
        logger.debug(f"    Accounts: {list(cluster_key)}")
        logger.debug(f"    Use cases: {[uc['name'] for uc in use_case_info_list]}")
        logger.debug(f"    Total Demand: RPM={cluster_rpm}, TPM={cluster_tpm}")
        logger.debug(f"    Total Capacity: RPM={cluster_rpm_capacity}, TPM={cluster_tpm_capacity}")
        logger.debug(
            f"    Status: {'✅ OK' if cluster_rpm <= cluster_rpm_capacity and cluster_tpm <= cluster_tpm_capacity else '❌ FAIL'}"
        )


def _check_cluster_quota_violations(
    adjusted_groups, model_name, use_case_key_to_display_name, capacities, env_name
):
    """Check each cluster for quota violations and print error messages.

    Args:
        adjusted_groups: Dictionary of clusters
        model_name: Name of the model
        use_case_key_to_display_name: Mapping from use case key to display name
        capacities: Account capacities
        env_name: Environment name

    Returns:
        bool: True if all checks pass, False if any violations found
    """
    all_checks_passed = True

    for cluster_key, use_cases in adjusted_groups.items():
        cluster_rpm, cluster_tpm, use_case_info_list = _calculate_usecases_model_demands(
            use_cases, use_case_key_to_display_name
        )

        cluster_rpm_capacity, cluster_tpm_capacity = _calculate_model_capacity(
            use_cases, model_name, capacities, set(cluster_key)
        )

        # Check for quota violations
        if cluster_rpm > cluster_rpm_capacity or cluster_tpm > cluster_tpm_capacity:
            all_checks_passed = False
            print(f"\n❌ Quota failures found in {env_name} environment.")
            print("=" * 80)
            print(f"Model            : {model_name}")
            # print(f"Cluster          : {cluster_key}")
            print(f"Usecases         : {', '.join([uc['name'] for uc in use_case_info_list])}")
            print(f"Usecase ids      : {', '.join([uc['id'] for uc in use_case_info_list])}")
            print(f"Account used     : {', '.join(sorted(cluster_key))}")

            if cluster_rpm > cluster_rpm_capacity:
                missing_rpm = cluster_rpm - cluster_rpm_capacity
                print(
                    f"Check failed RPM : The total RPM demands for this cluster is {cluster_rpm} while the total accounts RPM availability is {cluster_rpm_capacity}. Missing quota is {missing_rpm}"
                )

            if cluster_tpm > cluster_tpm_capacity:
                missing_tpm = cluster_tpm - cluster_tpm_capacity
                print(
                    f"Check failed TPM : The total TPM demands for this cluster is {cluster_tpm} while the total accounts TPM availability is {cluster_tpm_capacity}. Missing quota is {missing_tpm}"
                )

            print("=" * 80)

        # Check for warnings
        _check_account_sharing_warnings(use_cases, model_name, use_case_key_to_display_name)

    return all_checks_passed


def _check_account_sharing_warnings(use_cases, model_name, use_case_key_to_display_name):
    """Check for account sharing warnings.

    Args:
        use_cases: List of (use_case_name, demand_info, adjusted_demand_info) tuples
        model_name: Name of the model
        use_case_key_to_display_name: Mapping from use case key to display name
    """
    # Check for mixed unlimited and finite quotas
    has_unlimited = False
    has_finite = False

    for _, _, adjusted_demand_info in use_cases:
        if adjusted_demand_info["unlimited"]:
            has_unlimited = True
        else:
            has_finite = True

    if has_unlimited and has_finite:
        print(f"⚠️  Warning: Mixed unlimited and finite quotas detected for model {model_name}")
        print("=" * 80)
        print(f"Model            : {model_name}")

        # Get use case names and IDs
        use_case_names = []
        use_case_ids = []
        all_accounts = set()

        for use_case_name, demand_info, _ in use_cases:
            use_case_names.append(use_case_key_to_display_name.get(use_case_name, use_case_name))
            use_case_ids.append(use_case_name)
            all_accounts.update(demand_info["accounts"])

        print(f"Usecases         : {', '.join(use_case_names)}")
        print(f"Usecase ids      : {', '.join(use_case_ids)}")
        print(f"Account used     : {', '.join(sorted(all_accounts))}")
        print("=" * 80)


def check_quota_values(data, use_case_demands, capacities, env_name, show_status=False):
    """Check quota values for all models and use cases.

    Args:
        data: Configuration data
        use_case_demands: Distributed use case demands
        capacities: Account capacities
        env_name: Environment name
        show_status: Whether to show detailed status report

    Returns:
        bool: True if all checks pass, False otherwise
    """
    use_case_key_to_display_name = {}
    for use_case_key, use_case_info in data.get("permissions", {}).items():
        use_case_key_to_display_name[use_case_key] = use_case_info.get("name", use_case_key)

    model_to_account_groups = _group_use_cases_by_model_and_accounts(use_case_demands)

    all_checks_passed = True

    for model_name, account_groups in model_to_account_groups.items():
        # Create clusters with subset handling
        adjusted_groups = _find_overlapping_account_groups(account_groups)

        # Print debug information for all clusters
        _print_cluster_debug_info(
            adjusted_groups, model_name, use_case_key_to_display_name, capacities
        )

        # Check each cluster for quota violations
        model_checks_passed = _check_cluster_quota_violations(
            adjusted_groups, model_name, use_case_key_to_display_name, capacities, env_name
        )

        # Show status report if requested
        if show_status:
            _print_cluster_status_report(
                adjusted_groups, model_name, use_case_key_to_display_name, capacities, env_name
            )

        if not model_checks_passed:
            all_checks_passed = False

    return all_checks_passed


def _print_cluster_status_report(
    adjusted_groups, model_name, use_case_key_to_display_name, capacities, env_name
):
    """Print status report for all clusters in a model.

    Args:
        adjusted_groups: Dictionary of clusters
        model_name: Name of the model
        use_case_key_to_display_name: Mapping from use case key to display name
        capacities: Account capacities
        env_name: Environment name
    """
    print(f"\n📊 Cluster Status Report for {model_name} ({env_name})")
    print("=" * 80)

    for i, (cluster_key, use_cases) in enumerate(adjusted_groups.items(), 1):
        cluster_rpm, cluster_tpm, use_case_info_list = _calculate_usecases_model_demands(
            use_cases, use_case_key_to_display_name
        )

        cluster_rpm_capacity, cluster_tpm_capacity = _calculate_model_capacity(
            use_cases, model_name, capacities, set(cluster_key)
        )

        # Check if there are any unlimited demands
        has_unlimited_rpm = any(uc.get("rpm") == "unlimited" for uc in use_case_info_list)
        has_unlimited_tpm = any(uc.get("tpm") == "unlimited" for uc in use_case_info_list)

        # Format RPM display
        if has_unlimited_rpm:
            rpm_display = f"INFINITE / {cluster_rpm_capacity:,}"
            rpm_percentage_display = "N/A"
        else:
            rpm_percentage = (
                (cluster_rpm / cluster_rpm_capacity * 100) if cluster_rpm_capacity > 0 else 0
            )
            rpm_display = f"{cluster_rpm:,} / {cluster_rpm_capacity:,}"
            rpm_percentage_display = f"{rpm_percentage:.1f}% occupied"

        # Format TPM display
        if has_unlimited_tpm:
            tpm_display = f"INFINITE / {cluster_tpm_capacity:,}"
            tpm_percentage_display = "N/A"
        else:
            tpm_percentage = (
                (cluster_tpm / cluster_tpm_capacity * 100) if cluster_tpm_capacity > 0 else 0
            )
            tpm_display = f"{cluster_tpm:,} / {cluster_tpm_capacity:,}"
            tpm_percentage_display = f"{tpm_percentage:.1f}% occupied"

        # Determine status
        status = (
            "✅ OK"
            if cluster_rpm <= cluster_rpm_capacity and cluster_tpm <= cluster_tpm_capacity
            else "❌ FAIL"
        )

        print(f"Cluster {i}:")
        print(f"  Accounts: {', '.join(sorted(cluster_key))}")
        print(f"  Use cases: {', '.join([uc['name'] for uc in use_case_info_list])}")
        print(f"  Status: {status}")
        print(f"  RPM: {rpm_display} ({rpm_percentage_display})")
        print(f"  TPM: {tpm_display} ({tpm_percentage_display})")
        print()


def _setup_logging():
    """Set up logging configuration."""
    # Configure logging level based on environment variable or default to INFO
    log_level = os.environ.get("LOG_LEVEL", LOCAL_LOG_LEVEL).upper()
    numeric_level = getattr(logging, log_level, logging.INFO)

    # Configure the logger
    logging.basicConfig(level=numeric_level, format="%(message)s")


def main():
    """Script entry point."""
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Quota distribution and validation tool")
    parser.add_argument(
        "--status", action="store_true", help="Show detailed status report for each cluster"
    )
    args = parser.parse_args()

    _setup_logging()
    all_checks_passed = True

    for env_info in ENVIRONMENT_FILES:
        env_name = env_info["env_name"]
        file_path = env_info["file_path"]

        print(f"📂 Processing file: {file_path} ({env_name})")

        try:
            with open(file_path) as f:
                data = yaml.safe_load(f)

            # Extract use case demands and account capacities
            use_case_demands = distribute_demands(data.get("permissions", {}))
            capacities = data.get("account_limits", {})

            # Check quota values
            if check_quota_values(data, use_case_demands, capacities, env_name, args.status):
                print(f"✅ No quota issues found in {env_name} environment.")
            else:
                all_checks_passed = False

        except FileNotFoundError:
            print(f"❌ Error: File {file_path} not found.")
            all_checks_passed = False
        except json.JSONDecodeError as e:
            print(f"❌ Error: Invalid JSON in {file_path}: {e}")
            all_checks_passed = False
        except Exception as e:
            print(f"❌ Error processing {file_path}: {e}")
            all_checks_passed = False

    if not all_checks_passed:
        sys.exit(1)


if __name__ == "__main__":
    main()
