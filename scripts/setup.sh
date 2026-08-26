#!/usr/bin/env bash
# Swarm AI Studio Setup Script
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

echo "=== Setting up Swarm AI Studio ==="

# 1. Check Python version
PYTHON_BIN="python3"
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "Error: Python 3 is required but not installed." >&2
  exit 1
fi

echo "✓ Python found: $($PYTHON_BIN --version)"

# 2. Install Python dependencies
echo "Installing Python dependencies..."
"$PYTHON_BIN" -m pip install --quiet -r "${ROOT_DIR}/requirements.txt" || "$PYTHON_BIN" -m pip install -r "${ROOT_DIR}/requirements.txt"

# 3. Ensure executables are executable
chmod +x "${ROOT_DIR}/bin/swarm-studio"
chmod +x "${ROOT_DIR}/bin/qwen_oracle.sh"
chmod +x "${ROOT_DIR}/scripts/"*.sh

echo "✓ Permissions configured."
echo "=== Swarm AI Studio setup complete! ==="
echo "Run 'make run' or './bin/swarm-studio' to launch."
