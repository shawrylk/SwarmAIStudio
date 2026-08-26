"""
Unit Tests for Dynamic Skills Scanner & Capacity Catalog
"""

import unittest
from swarm.skills_scanner import (
    scan_all_installed_skills,
    classify_skill_category,
    format_skill_name,
    resolve_and_inject_skill,
    KNOWN_SKILL_CATEGORIES,
    CATEGORY_METADATA
)

class TestSkillsScanner(unittest.TestCase):
    def test_scan_finds_all_skills_and_validates_fields(self):
        skills = scan_all_installed_skills()
        self.assertGreaterEqual(len(skills), 53)
        
        # Verify Context7 and CBO Planner are present
        skill_ids = [s["id"] for s in skills]
        self.assertIn("context7-docs", skill_ids)
        self.assertIn("planner-cbo", skill_ids)
        self.assertIn("web-quality-audit", skill_ids)
        self.assertIn("security-review", skill_ids)
        self.assertIn("tdd", skill_ids)

        # Verify all mandatory fields on every skill
        for s in skills:
            self.assertIn("id", s)
            self.assertIn("name", s)
            self.assertIn("description", s)
            self.assertIn("category", s)
            self.assertIn("role", s)
            self.assertIn("tools", s)
            self.assertTrue(len(s["tools"]) > 0, f"Skill {s['id']} has empty tools")
            self.assertIn("path", s)

    def test_all_seven_categories_populated_and_no_empty_group(self):
        skills = scan_all_installed_skills()
        expected_categories = [
            "Security & Audit",
            "Testing & QA",
            "Architecture & Planning",
            "Frontend & UI/UX",
            "Codebase Intelligence & Git",
            "Agent Extensions & Customization",
            "Research & Documentation"
        ]
        
        cat_counts = {cat: 0 for cat in expected_categories}
        for s in skills:
            cat = s["category"]
            self.assertIn(cat, cat_counts, f"Unexpected category '{cat}' for skill '{s['id']}'")
            cat_counts[cat] += 1

        # Assert no category is empty
        for cat, count in cat_counts.items():
            self.assertGreater(count, 0, f"Category '{cat}' is empty!")
            self.assertIn(cat, CATEGORY_METADATA, f"Category '{cat}' missing from CATEGORY_METADATA")

        # Check expected minimum thresholds
        self.assertGreaterEqual(cat_counts["Security & Audit"], 8)
        self.assertGreaterEqual(cat_counts["Testing & QA"], 5)
        self.assertGreaterEqual(cat_counts["Architecture & Planning"], 8)
        self.assertGreaterEqual(cat_counts["Frontend & UI/UX"], 8)
        self.assertGreaterEqual(cat_counts["Codebase Intelligence & Git"], 9)
        self.assertGreaterEqual(cat_counts["Agent Extensions & Customization"], 6)
        self.assertGreaterEqual(cat_counts["Research & Documentation"], 8)

    def test_taxonomy_mapping_accuracy(self):
        skills = {s["id"]: s for s in scan_all_installed_skills()}

        # 1. Security & Audit
        sec_audit_skills = [
            "security-review", "best-practices", "gitnexus-taint-analysis",
            "forensics", "code-optimizer", "lint", "web-quality-audit", "review"
        ]
        for sid in sec_audit_skills:
            if sid in skills:
                self.assertEqual(skills[sid]["category"], "Security & Audit", f"{sid} should be in Security & Audit")

        # 2. Testing & QA
        qa_skills = ["test", "tdd", "debug-like-expert", "verify-before-complete", "gitnexus-debugging"]
        for sid in qa_skills:
            if sid in skills:
                self.assertEqual(skills[sid]["category"], "Testing & QA", f"{sid} should be in Testing & QA")

        # 3. Architecture & Planning
        arch_skills = [
            "design-an-interface", "api-design", "decompose-into-slices",
            "grill-me", "write-milestone-brief", "create-workflow", "planner-cbo"
        ]
        for sid in arch_skills:
            if sid in skills:
                self.assertEqual(skills[sid]["category"], "Architecture & Planning", f"{sid} should be in Architecture & Planning")

        # 4. Frontend & UI/UX
        ui_skills = [
            "frontend-design", "make-interfaces-feel-better", "react-best-practices",
            "userinterface-wiki", "web-design-guidelines", "core-web-vitals", "accessibility"
        ]
        for sid in ui_skills:
            if sid in skills:
                self.assertEqual(skills[sid]["category"], "Frontend & UI/UX", f"{sid} should be in Frontend & UI/UX")

        # 5. Codebase Intelligence & Git
        git_skills = [
            "gitnexus-cli", "gitnexus-exploring", "gitnexus-impact-analysis",
            "gitnexus-pdg-query", "gitnexus-pr-review", "gitnexus-refactoring",
            "github-workflows", "dependency-upgrade"
        ]
        for sid in git_skills:
            if sid in skills:
                self.assertEqual(skills[sid]["category"], "Codebase Intelligence & Git", f"{sid} should be in Codebase Intelligence & Git")

        # 6. Agent Extensions & Customization
        ext_skills = ["create-skill", "create-mcp-server", "create-gsd-extension", "find-skills", "agy-customizations"]
        for sid in ext_skills:
            if sid in skills:
                self.assertEqual(skills[sid]["category"], "Agent Extensions & Customization", f"{sid} should be in Agent Extensions & Customization")

        # 7. Research & Documentation
        doc_skills = ["write-docs", "spike-wrap-up", "btw", "handoff", "observability", "agent-browser", "ask-claude", "context7-docs"]
        for sid in doc_skills:
            if sid in skills:
                self.assertEqual(skills[sid]["category"], "Research & Documentation", f"{sid} should be in Research & Documentation")

    def test_heuristic_classification_fallback(self):
        # Test unknown skills categorized purely by heuristics
        cat_sec = classify_skill_category("custom-vuln-scanner", "Custom Vuln Scanner", "Scans for OWASP vulnerabilities and secret leaks")
        self.assertEqual(cat_sec, "Security & Audit")

        cat_qa = classify_skill_category("custom-tester", "Custom Tester", "Runs pytest assertions and unit tests")
        self.assertEqual(cat_qa, "Testing & QA")

        cat_ui = classify_skill_category("custom-widget", "Custom Widget", "Builds responsive React components with CSS and HTML")
        self.assertEqual(cat_ui, "Frontend & UI/UX")

        cat_ext = classify_skill_category("custom-plugin-builder", "Plugin Builder", "Creates MCP server tools and extension plugins")
        self.assertEqual(cat_ext, "Agent Extensions & Customization")

        cat_arch = classify_skill_category("custom-architect", "System Architect", "Produces RFC specifications, milestone PRDs and architecture slices")
        self.assertEqual(cat_arch, "Architecture & Planning")

        cat_git = classify_skill_category("custom-branch-manager", "Branch Manager", "Analyzes Git merge conflicts and repository commits")
        self.assertEqual(cat_git, "Codebase Intelligence & Git")

        cat_doc = classify_skill_category("custom-scribe", "Technical Scribe", "Author documentation, release notes, and markdown guides")
        self.assertEqual(cat_doc, "Research & Documentation")

    def test_format_skill_name(self):
        self.assertEqual(format_skill_name("tdd", ""), "TDD")
        self.assertEqual(format_skill_name("api-design", ""), "API Design")
        self.assertEqual(format_skill_name("create-mcp-server", ""), "Create MCP Server")
        self.assertEqual(format_skill_name("core-web-vitals", ""), "Core Web Vitals")
        self.assertEqual(format_skill_name("gitnexus-pdg-query", ""), "GitNexus PDG Query")

    def test_resolve_and_inject_skill_roles(self):
        # Dev role with TDD intent
        dev_res = resolve_and_inject_skill("dev", "Implement TDD red green refactor for user service")
        self.assertIn("skill_id", dev_res)
        self.assertIn("injection_prompt", dev_res)
        self.assertIn("DYNAMIC SKILL INJECTION", dev_res["injection_prompt"])
        self.assertTrue(len(dev_res["instructions"]) > 0)

        # QA role with verify intent
        qa_res = resolve_and_inject_skill("qa", "Verify unit test assertions and compiler diagnostics")
        self.assertIn("skill_id", qa_res)
        self.assertIn("injection_prompt", qa_res)

        # Security role with auth/injection intent
        sec_res = resolve_and_inject_skill("review", "Security audit for SQL injection and token leaks")
        self.assertIn("security", sec_res["skill_id"].lower() + " " + sec_res["category"].lower())
        self.assertIn("injection_prompt", sec_res)

        # Research role
        res_res = resolve_and_inject_skill("research", "Explore library docs and API design")
        self.assertIn("injection_prompt", res_res)

if __name__ == "__main__":
    unittest.main()

