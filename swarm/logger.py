"""
Swarm AI Studio Structured Logging & Debugging Subsystem
Logs all backend events, API calls, Git executions, and AI queries.
"""

import os
import sys
import time
import logging
from pathlib import Path
from typing import List, Dict, Any
from collections import deque
from swarm.config import SWARM_DIR

LOGS_DIR = SWARM_DIR / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)
ACTIVITY_LOG_FILE = LOGS_DIR / "activity.log"

# In-memory ring buffer for live debug drawer
LIVE_DEBUG_BUFFER = deque(maxlen=150)

# Configure file + stream logging
logger = logging.getLogger("SwarmStudio")
logger.setLevel(logging.DEBUG)

if not logger.handlers:
    # File handler
    fh = logging.FileHandler(ACTIVITY_LOG_FILE, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    formatter = logging.Formatter('[%(asctime)s] [%(levelname)s] [%(module)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
    fh.setFormatter(formatter)
    logger.addHandler(fh)

    # Console handler
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(formatter)
    logger.addHandler(ch)

def log_event(level: str, category: str, action: str, details: Dict[str, Any] = None, error: str = ""):
    """Logs an event both to logger and live debug buffer."""
    details = details or {}
    timestamp = time.strftime('%H:%M:%S', time.localtime())
    
    entry = {
        "timestamp": timestamp,
        "time_ms": int(time.time() * 1000),
        "level": level.upper(),
        "category": category,
        "action": action,
        "details": details,
        "error": error
    }
    
    LIVE_DEBUG_BUFFER.append(entry)
    
    msg = f"[{category.upper()}] {action}"
    if details:
        msg += f" | Details: {details}"
    if error:
        msg += f" | ERROR: {error}"

    if level.lower() == "error":
        logger.error(msg)
    elif level.lower() == "warn" or level.lower() == "warning":
        logger.warning(msg)
    elif level.lower() == "debug":
        logger.debug(msg)
    else:
        logger.info(msg)

def get_live_logs(limit: int = 50) -> List[Dict[str, Any]]:
    """Returns recent log entries for in-browser debug viewer."""
    return list(LIVE_DEBUG_BUFFER)[-limit:]
