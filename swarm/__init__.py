"""
Swarm AI Studio Package
"""

__version__ = "1.2.0"
__author__ = "Shawry & DeepMind AI Team"

from swarm.server import run_server
from swarm.orchestrator import plan_dynamic_swarm_for_task, process_advisor_chat
from swarm.git_engine import get_full_github_desktop_state, find_git_repos

__all__ = [
    "run_server",
    "plan_dynamic_swarm_for_task",
    "process_advisor_chat",
    "get_full_github_desktop_state",
    "find_git_repos"
]
