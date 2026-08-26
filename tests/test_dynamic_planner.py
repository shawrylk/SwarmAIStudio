"""
Unit Tests for Task-Aware Dynamic Swarm Planner
"""

import unittest
from swarm.orchestrator import plan_dynamic_swarm_for_task

class TestDynamicSwarmPlanner(unittest.TestCase):
    def test_file_search_scales_to_1_scout(self):
        plan = plan_dynamic_swarm_for_task("Where is the AccountService class located?", has_repo=True)
        self.assertEqual(len(plan), 1)
        self.assertIn("Scout", plan[0]["name"])

    def test_bug_fix_scales_to_4_surgical_agents(self):
        plan = plan_dynamic_swarm_for_task("Fix null reference exception in PaymentEngine", has_repo=True)
        self.assertEqual(len(plan), 4)
        names = [a["name"] for a in plan]
        self.assertTrue(any("Scout" in n for n in names))
        self.assertTrue(any("Draftsman" in n for n in names))
        self.assertTrue(any("QA" in n or "LSP" in n for n in names))
        self.assertTrue(any("Gatekeeper" in n for n in names))

    def test_deep_audit_scales_to_6_specialists(self):
        plan = plan_dynamic_swarm_for_task("Run a deep security, performance, and architecture audit on this repo", has_repo=True)
        self.assertEqual(len(plan), 6)
        skills = [a["skill"] for a in plan]
        self.assertTrue(any("OWASP" in s for s in skills))
        self.assertTrue(any("Latency" in s for s in skills))
        self.assertTrue(any("Architecture" in s for s in skills))

    def test_general_chat_scales_to_3_solution_architects(self):
        plan = plan_dynamic_swarm_for_task("Explain distributed consensus algorithms", has_repo=False)
        self.assertEqual(len(plan), 3)

if __name__ == "__main__":
    unittest.main()
