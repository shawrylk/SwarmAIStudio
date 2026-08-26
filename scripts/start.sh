#!/usr/bin/env bash
# Swarm AI Studio Production Background Launcher
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

PORT="${SWARM_PORT:-8080}"

# Stop any running instances on this port
fuser -k "${PORT}/tcp" >/dev/null 2>&1 || true

echo "Starting Swarm AI Studio in background on port ${PORT}..."
nohup "${ROOT_DIR}/bin/swarm" web --port "$PORT" > "${ROOT_DIR}/swarm_studio.log" 2>&1 &
PID=$!

sleep 1.2
if ps -p "$PID" >/dev/null 2>&1; then
  echo "✓ Swarm AI Studio started successfully (PID: $PID)!"
  echo "Open: http://localhost:${PORT}"
else
  echo "Error starting Swarm AI Studio. Check log: ${ROOT_DIR}/swarm_studio.log" >&2
  exit 1
fi
