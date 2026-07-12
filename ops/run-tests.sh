#!/usr/bin/env bash
# Run pytest suites for both services in a dedicated test virtualenv using Python 3.13.

set -euo pipefail

OPS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$OPS_DIR/.." && pwd)"
cd "$REPO_DIR"

echo "=== Running Python Test Suite ==="

# Set up test virtualenv
VENV_DIR="$REPO_DIR/.venv-tests"
if [[ ! -d "$VENV_DIR" ]]; then
  echo "Creating test virtualenv at $VENV_DIR..."
  if command -v python3.13 >/dev/null 2>&1; then
    python3.13 -m venv "$VENV_DIR"
  else
    python3 -m venv "$VENV_DIR"
  fi
fi

# Activate virtualenv
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

# Update pip
pip install --quiet --upgrade pip

# Install dependencies for both services and pytest tools
echo "Installing dependencies..."
pip install --quiet \
  -r services/nova-core/requirements.txt \
  -r services/ops-bridge/requirements.txt \
  pytest \
  pytest-asyncio \
  ruff \
  mypy

echo "Running nova-core tests..."
PYTHONPATH="$REPO_DIR/services/nova-core" pytest services/nova-core/tests

echo "Running ops-bridge tests..."
PYTHONPATH="$REPO_DIR/services/ops-bridge" pytest services/ops-bridge/tests

echo "Running ruff lint..."
ruff check services/

echo "Running mypy type checking..."
mypy services/nova-core/app/ services/ops-bridge/app.py

echo "=== All tests, lint, and type checks passed successfully! ==="
