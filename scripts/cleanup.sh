#!/bin/bash
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

# Cleanup script to remove temporary files and caches

echo "Cleaning up temporary files and caches..."

# Remove Python cache files
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null
find . -type f -name "*.pyc" -delete 2>/dev/null
find . -type f -name "*.pyo" -delete 2>/dev/null

# Remove coverage files (including nested)
find . -type d -name "htmlcov" -exec rm -rf {} + 2>/dev/null
find . -type f -name ".coverage*" -delete 2>/dev/null
find . -type f -name "*coverage.xml" -delete 2>/dev/null
find . -type f -name "*test-results.xml" -delete 2>/dev/null

# Remove cache directories (including nested)
find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null
find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null
find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null

# Remove build and distribution directories
find . -type d -name "dist" -exec rm -rf {} + 2>/dev/null
find . -type d -name "build" -exec rm -rf {} + 2>/dev/null
find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null

# Remove Jupyter notebook checkpoints
find . -type d -name ".ipynb_checkpoints" -exec rm -rf {} + 2>/dev/null

# Remove IDE and editor temporary files
find . -type f -name "*.swp" -delete 2>/dev/null
find . -type f -name "*.swo" -delete 2>/dev/null
find . -type f -name "*~" -delete 2>/dev/null
find . -type f -name ".DS_Store" -delete 2>/dev/null
find . -type f -name "Thumbs.db" -delete 2>/dev/null
find . -type f -name "*.bak" -delete 2>/dev/null
find . -type f -name "*.orig" -delete 2>/dev/null

# Remove other temporary files
find . -type f -name "*.tmp" -delete 2>/dev/null
find . -type f -name "*.log" -delete 2>/dev/null

echo "Cleanup completed!"
