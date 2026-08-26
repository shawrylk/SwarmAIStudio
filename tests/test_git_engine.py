"""
Unit Tests for GitHub Desktop Git Engine & Worktree Manager
"""

import unittest
from pathlib import Path
from swarm.git_engine import (
    find_git_repos,
    get_full_github_desktop_state,
    list_worktrees,
    get_clean_branches,
    switch_or_create_branch
)

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
            self.assertIn("worktrees", state)

    def test_clean_branches_list(self):
        repos = find_git_repos()
        if repos:
            repo_path = repos[0]["path"]
            branches = get_clean_branches(repo_path)
            self.assertIsInstance(branches, list)
            if branches:
                self.assertIn("name", branches[0])
                self.assertIn("ref", branches[0])

    def test_worktrees_listing(self):
        repos = find_git_repos()
        if repos:
            repo_path = repos[0]["path"]
            worktrees = list_worktrees(repo_path)
            self.assertIsInstance(worktrees, list)
            if worktrees:
                self.assertIn("path", worktrees[0])
                self.assertIn("branch", worktrees[0])

if __name__ == "__main__":
    unittest.main()
