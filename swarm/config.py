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

# Auto-Resume on Server Startup (configurable via env SWARM_AUTO_RESUME=1)
AUTO_RESUME_ON_START = os.environ.get("SWARM_AUTO_RESUME", "1").lower() in ("1", "true", "yes")

# Parallel Multi-Agent Concurrency Settings
MAX_CONCURRENT_AGENTS = int(os.environ.get("SWARM_MAX_CONCURRENCY", "8"))
PARALLEL_AUDIT_PHASE = os.environ.get("SWARM_PARALLEL_AUDIT", "1").lower() in ("1", "true", "yes")
PARALLEL_TASK_EXECUTION = os.environ.get("SWARM_PARALLEL_TASKS", "1").lower() in ("1", "true", "yes")
MULTI_WORKTREE_DAG = os.environ.get("SWARM_MULTI_WORKTREE_DAG", "1").lower() in ("1", "true", "yes")

# Dev-role execution engine. "pi" routes code drafting through the Pi coding
# agent's tool loop so the model can read a file before rewriting it; "raw" uses
# the legacy single-completion call. "auto" is equivalent to "pi" when the CLI
# is installed and falls back automatically when it is not.
DEV_AGENT_ENGINE = os.environ.get("SWARM_DEV_ENGINE", "auto").strip().lower()
PI_AGENT_TIMEOUT = float(os.environ.get("SWARM_PI_TIMEOUT", "900"))

# Persistent Directory Structure
SWARM_DIR = Path.home() / ".swarm"
SESSIONS_DIR = SWARM_DIR / "sessions"
LOOP_SESSIONS_DIR = SWARM_DIR / "loop_sessions"
ARTIFACTS_DIR = SWARM_DIR / "artifacts"
RULES_DIR = SWARM_DIR / "rules"
GLOBAL_RULES_FILE = SWARM_DIR / "global_rules.md"
MODELS_CONFIG_FILE = SWARM_DIR / "model_assignments.json"

SWARM_DIR.mkdir(parents=True, exist_ok=True)
SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
LOOP_SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
RULES_DIR.mkdir(parents=True, exist_ok=True)

# Package paths
PKG_DIR = Path(__file__).resolve().parent.parent
WEB_DIR = PKG_DIR / "web"
BIN_DIR = PKG_DIR / "bin"
QWEN_ORACLE_SCRIPT = BIN_DIR / "qwen_oracle.sh"
if not QWEN_ORACLE_SCRIPT.exists():
    fallback_qwen = Path.home() / "qwen_oracle.sh"
    if fallback_qwen.exists():
        QWEN_ORACLE_SCRIPT = fallback_qwen


def resolve_within(candidate, base_dir):
    """Resolve `candidate` and return it only if it lives inside `base_dir`.

    Returns a resolved Path on success, or None if the path escapes the base
    (via .., symlinks, or an absolute path). Used to confine filesystem access
    exposed over the LAN-facing HTTP API.
    """
    try:
        base = Path(base_dir).resolve()
        cand = Path(str(candidate))
        target = cand if cand.is_absolute() else (base / cand)
        target = target.resolve()
        target.relative_to(base)
        return target
    except (ValueError, OSError):
        return None


def script_is_runnable(path) -> bool:
    """True only if `path` exists and has an executable bit set."""
    try:
        p = Path(path)
        return p.exists() and os.access(str(p), os.X_OK)
    except OSError:
        return False
