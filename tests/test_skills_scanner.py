"""
Unit Tests for Dynamic Skills Scanner & Capacity Catalog
"""

import unittest
from swarm.skills_scanner import scan_all_installed_skills

class TestSkillsScanner(unittest.TestCase):
    def test_scan_finds_skills_and_categories(self):
        skills = scan_all_installed_skills()
        self.assertGreaterEqual(len(skills), 20)
        
        # Verify Context7 and CBO Planner are present
        skill_ids = [s["id"] for s in skills]
        self.assertIn("context7-docs", skill_ids)
        self.assertIn("planner-cbo", skill_ids)

        # Verify fields
        for s in skills:
            self.assertIn("name", s)
            self.assertIn("description", s)
            self.assertIn("category", s)
            self.assertIn("role", s)
            self.assertIn("tools", s)

if __name__ == "__main__":
    unittest.main()
