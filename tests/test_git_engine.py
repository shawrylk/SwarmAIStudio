"""
Unit Tests for GitHub Desktop Git Engine
"""

import unittest
from pathlib import Path
from swarm.git_engine import find_git_repos, get_full_github_desktop_state

class TestGitEngine(unittest.TestCase):
    def test_find_git_repos_discovers_repositories(self):
        repos = find_git_repos()
        self.assertIsInstance(repos, list)
        if repos:
            self.assertIn("name", repos[0])
            self.assertIn("path", repos[0])

    def test_get_full_github_desktop_state(self):
        repos = find_git_repos()
        if repos:
            repo_path = repos[0]["path"]
            state = get_full_github_desktop_state(repo_path)
            self.assertTrue(state["active"])
            self.assertIn("branch", state)
            self.assertIn("changed_files", state)
            self.assertIn("history", state)
            self.assertIn("branches", state)

if __name__ == "__main__":
    unittest.main()
