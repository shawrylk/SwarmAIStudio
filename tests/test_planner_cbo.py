"""
Unit Tests for Cost-Based Optimizer (CBO) & Swarm DAG Execution Planner
"""

import unittest
from swarm.planner_cbo import (
    analyze_intent_statistics,
    enumerate_candidate_plans,
    optimize_and_select_best_plan,
    SwarmPlanNode,
    SwarmExecutionPlan
)

class TestPlannerCBO(unittest.TestCase):
    def test_analyze_intent_statistics_complexity(self):
        stats = analyze_intent_statistics("Run a deep security audit and refactor database queries", repo_ctx={"name": "BankFlow"})
        self.assertGreaterEqual(stats["complexity_score"], 6)
        self.assertTrue(stats["has_audit_keywords"])
        self.assertTrue(stats["has_code_keywords"])

    def test_plan_enumeration_generates_three_candidates(self):
        stats = analyze_intent_statistics("Implement OAuth2 authentication", repo_ctx={})
        candidates = enumerate_candidate_plans(stats, "Implement OAuth2 authentication")
        self.assertEqual(len(candidates), 3)
        
        plan_ids = [c.plan_id for c in candidates]
        self.assertIn("plan_fast_latency", plan_ids)
        self.assertIn("plan_multi_verified", plan_ids)
        self.assertIn("plan_c7_consensus", plan_ids)

    def test_cbo_selects_fast_for_simple_lookup(self):
        plan, candidates, stats = optimize_and_select_best_plan("Where is the user model file?", repo_ctx={})
        self.assertEqual(plan.plan_id, "plan_fast_latency")
        self.assertIn("EXPLAIN", plan.generate_explain_plan())

    def test_cbo_selects_context7_for_documentation_task(self):
        plan, candidates, stats = optimize_and_select_best_plan("Show me latest Context7 documentation on FastAPI dependencies", repo_ctx={})
        self.assertEqual(plan.plan_id, "plan_c7_consensus")
        self.assertTrue(any(n.operator == "DOC_FETCH" for n in plan.nodes))

    def test_explain_plan_formatting(self):
        plan, _, _ = optimize_and_select_best_plan("Deep review of repository", repo_ctx={"name": "BankFlow"})
        explain = plan.generate_explain_plan()
        self.assertIn("SWARM QUERY PLAN", explain)
        self.assertIn("Cost Score", explain)
        self.assertIn("EXECUTION DAG", explain)

if __name__ == "__main__":
    unittest.main()
