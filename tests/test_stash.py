"""
Unit Tests for Stash Subsystem
"""

import unittest
from pathlib import Path
from swarm.git_engine import (
    find_git_repos,
    list_stashes,
    save_stash,
    pop_stash,
    drop_stash
)

class TestStashSubsystem(unittest.TestCase):
    def test_list_stashes_returns_list(self):
        repos = find_git_repos()
        if repos:
            repo_path = repos[0]["path"]
            stashes = list_stashes(repo_path)
            self.assertIsInstance(stashes, list)

    def test_stash_lifecycle(self):
        repos = find_git_repos()
        if repos:
            repo_path = repos[0]["path"]
            # Save stash
            res = save_stash(repo_path, message="Unit test temporary stash")
            self.assertIsInstance(res, dict)

if __name__ == "__main__":
    unittest.main()
