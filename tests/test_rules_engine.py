"""
Unit Tests for Swarm Architecture Rules Engine (Global & Project-Specific)
"""

import unittest
import tempfile
from pathlib import Path
from swarm.rules_engine import (
    get_global_rules,
    save_global_rules,
    discover_project_rules,
    format_enforced_rules_prompt
)

class TestRulesEngine(unittest.TestCase):
    def test_global_rules_contains_clean_architecture_pillars(self):
        rules = get_global_rules()
        self.assertIn("Small, Single-Responsibility Functions", rules)
        self.assertIn("One Domain Class Per File", rules)
        self.assertIn("Dependency Injection", rules)
        self.assertIn("High Refactorability", rules)

    def test_project_rule_discovery(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            rule_file = tmppath / "RULE.md"
            rule_file.write_text("# Project Custom Rule\nMust use Repository pattern.", encoding="utf-8")

            res = discover_project_rules(str(tmppath))
            self.assertTrue(res["has_rules"])
            self.assertEqual(res["source"], "RULE.md")
            self.assertIn("Repository pattern", res["content"])

    def test_format_enforced_rules_prompt_combines_global_and_project(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            (tmppath / "GEMINI.md").write_text("# Sub-agents must run sequential", encoding="utf-8")
            
            prompt = format_enforced_rules_prompt(str(tmppath))
            self.assertIn("GLOBAL ARCHITECTURE RULES", prompt)
            self.assertIn("PROJECT-SPECIFIC RULES (GEMINI.md)", prompt)
            self.assertIn("Sub-agents must run sequential", prompt)

    def test_format_enforced_rules_prompt_includes_dynamic_learned_rules(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            learned = [
                "RULE: In C# .NET solutions, always include using System.Collections.Generic;",
                "RULE: Never remove existing namespace imports in domain entities."
            ]
            prompt = format_enforced_rules_prompt(str(tmppath), learned_rules=learned)
            self.assertIn("DYNAMIC LESSONS LEARNED & EVOLVED INVARIANTS", prompt)
            self.assertIn("In C# .NET solutions, always include using System.Collections.Generic;", prompt)
            self.assertIn("Never remove existing namespace imports", prompt)

if __name__ == "__main__":
    unittest.main()
