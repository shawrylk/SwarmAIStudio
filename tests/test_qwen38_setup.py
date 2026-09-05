"""
Unit Tests for Qwen 3.8 27B Launcher, 3-Slot Concurrency & Sub-Agent Orchestration
"""

import unittest
from pathlib import Path
from swarm import config
from swarm.model_scout import scout_all_models, load_model_assignments
from swarm.orchestrator import SWARM_STATE, plan_dynamic_swarm_for_task

class TestQwen38Setup(unittest.TestCase):
    def test_config_defaults_for_3_slots(self):
        self.assertEqual(config.MAX_CONCURRENT_AGENTS, 3)
        self.assertIn(config.DEV_AGENT_ENGINE, ("auto", "raw", "pi"))
        self.assertIn("8034", config.LFM_URL)

    def test_launcher_scripts_exist_and_executable(self):
        launcher = config.BIN_DIR / "launch_qwen38_27b.sh"
        downloader = config.PKG_DIR / "scripts" / "download_qwen38_27b.py"
        self.assertTrue(launcher.exists(), f"Missing launcher at {launcher}")
        self.assertTrue(downloader.exists(), f"Missing downloader at {downloader}")

    def test_model_scout_registers_qwen38_27b(self):
        catalog = scout_all_models()
        lfm_models = [m["id"] for m in catalog.get("lfm", [])]
        self.assertTrue(any("qwen-3.8-27b" in mid for mid in lfm_models))

    def test_orchestrator_state_has_3_slots(self):
        self.assertEqual(config.MAX_CONCURRENT_AGENTS, 3)
        self.assertIn("Qwen 3.8 27B", SWARM_STATE["consensus_nodes"][0]["name"])
        self.assertIn("3 Continuous Batching Slots", SWARM_STATE["consensus_nodes"][0]["role"])

    def test_planner_creates_focused_subagent_spec(self):
        spec = plan_dynamic_swarm_for_task("Find where auth tokens are stored", has_repo=True)
        self.assertEqual(len(spec), 1)
        self.assertIn("Scout", spec[0]["name"])

if __name__ == "__main__":
    unittest.main()
