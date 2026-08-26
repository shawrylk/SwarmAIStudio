"""
Unit Tests for Autonomous Loop Agent Engine & Advisor Ping
"""

import unittest
import asyncio
from unittest.mock import patch, AsyncMock
from swarm.loop_engine import (
    get_loop_state,
    start_loop,
    pause_loop,
    resume_loop,
    stop_loop,
    decompose_goal_into_tasks,
    ping_lead_advisor
)

class TestLoopEngine(unittest.TestCase):
    def tearDown(self):
        stop_loop()

    def test_loop_state_structure(self):
        state = get_loop_state()
        self.assertIn("status", state)
        self.assertIn("tasks", state)
        self.assertIn("advisor_pings", state)

    def test_loop_lifecycle_controls(self):
        with patch("swarm.loop_engine._thread_worker"):
            # Test start
            res = start_loop("Test Feature Loop", repo_path="")
            self.assertTrue(res["success"])
            self.assertEqual(get_loop_state()["status"], "running")

            # Test pause
            pause_res = pause_loop()
            self.assertTrue(pause_res["success"])
            self.assertEqual(get_loop_state()["status"], "paused")

            # Test resume
            resume_res = resume_loop()
            self.assertTrue(resume_res["success"])
            self.assertEqual(get_loop_state()["status"], "running")

            # Test stop
            stop_res = stop_loop()
            self.assertTrue(stop_res["success"])
            self.assertEqual(get_loop_state()["status"], "idle")

    def test_decompose_tasks_fallback(self):
        async def run_test():
            with patch("swarm.orchestrator.query_gemini", new_callable=AsyncMock) as mock_gemini:
                mock_gemini.return_value = """[
                    {"title": "Architecture Spec", "role": "pm", "description": "Spec", "acceptance_criteria": "Done"},
                    {"title": "Code Draft", "role": "dev", "description": "Dev", "acceptance_criteria": "Done"},
                    {"title": "QA Tests", "role": "qa", "description": "QA", "acceptance_criteria": "Done"}
                ]"""
                tasks = await decompose_goal_into_tasks("Implement Redis Lock", "")
                self.assertEqual(len(tasks), 3)
                self.assertEqual(tasks[0]["role"], "pm")
                self.assertEqual(tasks[1]["role"], "dev")
                self.assertEqual(tasks[2]["role"], "qa")

        asyncio.run(run_test())

    def test_advisor_ping(self):
        async def run_test():
            with patch("swarm.orchestrator.query_gemini", new_callable=AsyncMock) as mock_gemini:
                mock_gemini.return_value = "Use RS256 for asymmetric signature verification."
                ans = await ping_lead_advisor("Surgical Draftsman", "dev", "RS256 vs HS256?", "Auth task")
                self.assertIn("RS256", ans)
                state = get_loop_state()
                self.assertGreater(len(state["advisor_pings"]), 0)

        asyncio.run(run_test())

if __name__ == "__main__":
    unittest.main()
