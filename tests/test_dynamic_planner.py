"""
Unit Tests for Task-Aware Dynamic Planner
Validates that the planner selects the right focused agent configuration per task type.
"""

import unittest
from swarm.orchestrator import plan_dynamic_swarm_for_task

class TestDynamicSwarmPlanner(unittest.TestCase):
    def test_file_search_scales_to_1_scout(self):
        plan = plan_dynamic_swarm_for_task("Where is the AccountService class located?", has_repo=True)
        self.assertEqual(len(plan), 1)
        self.assertIn("Scout", plan[0]["name"])

    def test_docs_query_selects_documentation_agent(self):
        plan = plan_dynamic_swarm_for_task("Show me Context7 documentation and latest API example for FastAPI Depends", has_repo=True)
        self.assertEqual(len(plan), 1)
        self.assertIn("Doc", plan[0]["name"])

    def test_bug_fix_selects_focused_agent(self):
        plan = plan_dynamic_swarm_for_task("Fix null reference exception in PaymentEngine", has_repo=True)
        self.assertEqual(len(plan), 1)
        self.assertIsNotNone(plan[0]["prompt_template"])

    def test_code_review_selects_reviewer(self):
        plan = plan_dynamic_swarm_for_task("Run a deep security and performance audit on this repo", has_repo=True)
        self.assertEqual(len(plan), 1)
        self.assertIn("Review", plan[0]["skill"])

    def test_general_chat_selects_assistant(self):
        plan = plan_dynamic_swarm_for_task("Explain distributed consensus algorithms", has_repo=False)
        self.assertEqual(len(plan), 1)
        self.assertIn("agent_core", plan[0]["id"])

if __name__ == "__main__":
    unittest.main()
