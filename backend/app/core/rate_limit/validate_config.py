#!/usr/bin/env python3
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Validate rate limit configuration files against schema."""

import json
import sys
from pathlib import Path

import yaml
from jsonschema import ValidationError, validate


def main():
    """Validate rate limit configuration files."""
    if len(sys.argv) < 2:
        print("Usage: validate_config.py <config_file>...")
        sys.exit(1)

    # Load schema
    schema_path = Path(__file__).parent / "config" / "schema.json"
    try:
        with open(schema_path) as f:
            schema = json.load(f)
    except Exception as e:
        print(f"❌ Error loading schema: {e}")
        sys.exit(1)

    all_errors = []

    for config_file in sys.argv[1:]:
        config_path = Path(config_file)

        if not config_path.exists():
            all_errors.append(f"Config file not found: {config_file}")
            continue

        try:
            with open(config_path) as f:
                if config_path.suffix == ".yaml" or config_path.suffix == ".yml":
                    config = yaml.safe_load(f)
                else:
                    config = json.load(f)
        except (json.JSONDecodeError, yaml.YAMLError) as e:
            all_errors.append(f"Invalid format in {config_file}: {e}")
            continue
        except Exception as e:
            all_errors.append(f"Error reading {config_file}: {e}")
            continue

        # Validate against schema
        try:
            validate(instance=config, schema=schema)

            # Additional business rule: require 'default' permission
            if "default" not in config.get("permissions", {}):
                all_errors.append(f"{config_file}: Missing required 'default' permission")

        except ValidationError as e:
            all_errors.append(f"{config_file}: {e.message}")

    if all_errors:
        print("Rate limit configuration validation failed:")
        for error in all_errors:
            print(f"  ❌ {error}")
        sys.exit(1)

    print("✅ All rate limit configurations are valid")


if __name__ == "__main__":
    main()
