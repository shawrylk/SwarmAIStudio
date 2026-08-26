"""
Swarm AI Studio Configuration & Environment Paths
"""

import os
from pathlib import Path

PORT = int(os.environ.get("SWARM_PORT", "8080"))
HOST = os.environ.get("SWARM_HOST", "0.0.0.0")

# Local GPU Engine URL (Continuous Batching LFM 2.5 on port 8034)
LFM_URL = os.environ.get("LFM_URL", "http://localhost:8034/v1/chat/completions")
LFM_HEALTH_URL = os.environ.get("LFM_HEALTH_URL", "http://localhost:8034/health")

# Persistent Directory Structure
SWARM_DIR = Path.home() / ".swarm"
SESSIONS_DIR = SWARM_DIR / "sessions"
ARTIFACTS_DIR = SWARM_DIR / "artifacts"
MODELS_CONFIG_FILE = SWARM_DIR / "model_assignments.json"

SWARM_DIR.mkdir(parents=True, exist_ok=True)
SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

# Package paths
PKG_DIR = Path(__file__).resolve().parent.parent
WEB_DIR = PKG_DIR / "web"
BIN_DIR = PKG_DIR / "bin"
QWEN_ORACLE_SCRIPT = BIN_DIR / "qwen_oracle.sh"
if not QWEN_ORACLE_SCRIPT.exists():
    fallback_qwen = Path.home() / "qwen_oracle.sh"
    if fallback_qwen.exists():
        QWEN_ORACLE_SCRIPT = fallback_qwen
