"""
Unit Tests for Grouped Artifacts Vault
"""

import unittest
from swarm.artifacts import save_artifact_to_disk, scan_all_artifacts

class TestArtifacts(unittest.TestCase):
    def test_artifact_saved_and_grouped(self):
        # 1. Save artifact for a named repo
        res = save_artifact_to_disk(
            title="Unit Test Spec",
            filename="TEST_SPEC.md",
            content="# Test Specification Content",
            repo_path="/home/shawry/Documents/GitHub/SwarmAIStudio"
        )
        self.assertEqual(res["repo_name"], "SwarmAIStudio")
        self.assertTrue(res["filename"].endswith(".md"))

        # 2. Scan all artifacts
        grouped = scan_all_artifacts("/home/shawry/Documents/GitHub/SwarmAIStudio")
        self.assertIn("groups", grouped)
        self.assertIn("total_count", grouped)
        
        # Verify SwarmAIStudio group exists
        group_names = [g["repo_name"] for g in grouped["groups"]]
        self.assertIn("SwarmAIStudio", group_names)

if __name__ == "__main__":
    unittest.main()
