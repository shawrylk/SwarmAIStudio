#!/usr/bin/env bash
# Swarm AI Studio Development Runner
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

PORT="${SWARM_PORT:-8080}"

fuser -k "${PORT}/tcp" >/dev/null 2>&1 || true

echo "Launching Swarm AI Studio in foreground (interactive dev mode)..."
exec "${ROOT_DIR}/bin/swarm-studio" --port "$PORT"
