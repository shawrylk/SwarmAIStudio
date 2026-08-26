#!/usr/bin/env bash
# Swarm AI Studio Graceful Shutdown
set -euo pipefail

PORT="${SWARM_PORT:-8080}"

echo "Stopping Swarm AI Studio on port ${PORT}..."
fuser -k "${PORT}/tcp" || true
echo "✓ Swarm AI Studio stopped."
