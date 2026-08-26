"""
Unit Tests for Swarm Configuration & Concurrency Environment Overrides
"""

import os
import importlib
import unittest
from unittest.mock import patch

class TestSwarmConfig(unittest.TestCase):
    def test_default_concurrency_settings(self):
        import swarm.config as config
        importlib.reload(config)
        self.assertEqual(config.MAX_CONCURRENT_AGENTS, 8)
        self.assertTrue(config.PARALLEL_AUDIT_PHASE)
        self.assertTrue(config.PARALLEL_TASK_EXECUTION)
        self.assertTrue(config.MULTI_WORKTREE_DAG)

    def test_env_var_overrides(self):
        env_patches = {
            "SWARM_MAX_CONCURRENCY": "16",
            "SWARM_PARALLEL_AUDIT": "0",
            "SWARM_PARALLEL_TASKS": "false",
            "SWARM_MULTI_WORKTREE_DAG": "no"
        }
        with patch.dict(os.environ, env_patches):
            import swarm.config as config
            importlib.reload(config)
            self.assertEqual(config.MAX_CONCURRENT_AGENTS, 16)
            self.assertFalse(config.PARALLEL_AUDIT_PHASE)
            self.assertFalse(config.PARALLEL_TASK_EXECUTION)
            self.assertFalse(config.MULTI_WORKTREE_DAG)

        # Reload back to standard environment
        import swarm.config as config
        importlib.reload(config)

    def test_directory_paths_exist(self):
        import swarm.config as config
        self.assertTrue(config.SWARM_DIR.exists())
        self.assertTrue(config.SESSIONS_DIR.exists())
        self.assertTrue(config.LOOP_SESSIONS_DIR.exists())
        self.assertTrue(config.ARTIFACTS_DIR.exists())
        self.assertTrue(config.RULES_DIR.exists())

if __name__ == "__main__":
    unittest.main()
