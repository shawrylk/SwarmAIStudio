"""
Loop git-lifecycle tests: branch delete after merge, and graceful degradation of
the GitHub Projects board when the `project` token scope is absent.
"""

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from swarm.git_engine import (
    switch_or_create_branch,
    commit_changes,
    merge_branch,
    git_delete_branch,
    gh_project_ensure,
    gh_project_add_task,
)


def _git(repo, *args):
    subprocess.run(["git", "-C", repo, *args], check=True, capture_output=True, text=True)


class TestBranchLifecycle(unittest.TestCase):
    def test_merge_then_delete_branch(self):
        with tempfile.TemporaryDirectory() as tmp:
            _git(tmp, "init", "-q")
            _git(tmp, "config", "user.email", "t@t")
            _git(tmp, "config", "user.name", "t")
            (Path(tmp) / "a.txt").write_text("base", encoding="utf-8")
            _git(tmp, "add", "-A")
            _git(tmp, "commit", "-qm", "base")
            # rename default branch to main for determinism
            _git(tmp, "branch", "-M", "main")

            # feature branch with a real change
            switch_or_create_branch(tmp, "swarm/loop-x", create=True, start_point="main")
            (Path(tmp) / "b.txt").write_text("feature", encoding="utf-8")
            commit = commit_changes(tmp, "feat: add b")
            self.assertTrue(commit["committed"])

            # merge into main
            merged = merge_branch(tmp, source_branch="swarm/loop-x", target_branch="main")
            self.assertTrue(merged["merged"])

            # delete the merged branch
            deleted = git_delete_branch(tmp, "swarm/loop-x", force=False)
            self.assertTrue(deleted["success"])

            branches = subprocess.run(["git", "-C", tmp, "branch"], capture_output=True, text=True).stdout
            self.assertNotIn("swarm/loop-x", branches)
            # the file landed on main
            self.assertTrue((Path(tmp) / "b.txt").exists())


class TestProjectBoardDegradation(unittest.TestCase):
    def test_board_noop_without_scope(self):
        with patch("swarm.git_engine.gh_project_scope_ok", return_value=False):
            res = gh_project_ensure("/tmp", "Some board")
            self.assertFalse(res["available"])
            self.assertIn("scope", res["reason"].lower())
            item = gh_project_add_task("/tmp", "owner", 1, "task")
            self.assertFalse(item["success"])


if __name__ == "__main__":
    unittest.main()


class TestToolCallExtraction(unittest.TestCase):
    def test_extracts_native_tool_call_format(self):
        from swarm.git_engine import extract_code_blocks_and_write
        out = ("<|tool_call_start|>[write(path='utils/mathx.py', content='def add(a, b):\\n    return a + b\\n'), "
               "write(path=\"tests/test_mathx.py\", content='def test_add():\\n    assert add(1,2)==3\\n')]<|tool_call_end|>")
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run(["git", "-C", tmp, "init", "-q"], check=True)
            written = extract_code_blocks_and_write(tmp, out)
            paths = sorted(w["path"] for w in written)
            self.assertEqual(paths, ["tests/test_mathx.py", "utils/mathx.py"])
            self.assertIn("def add", (Path(tmp) / "utils/mathx.py").read_text())

    def test_tool_call_rejects_traversal(self):
        from swarm.git_engine import extract_code_blocks_and_write
        out = "<|tool_call_start|>[write(path='../../etc/evil', content='x')]<|tool_call_end|>"
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run(["git", "-C", tmp, "init", "-q"], check=True)
            self.assertEqual(extract_code_blocks_and_write(tmp, out), [])


class TestTruncationSalvage(unittest.TestCase):
    def test_salvages_complete_writes_before_truncation(self):
        from swarm.git_engine import extract_code_blocks_and_write
        # Two complete writes, then a third truncated mid-content (no closing quote/paren/tag)
        out = ("<|tool_call_start|>[write(path='a.py', content='print(1)\\n'), "
               "write(path='b.py', content='print(2)\\n'), "
               "write(path='c.py', content='def big():\\n    x = 'unterminated")
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run(["git", "-C", tmp, "init", "-q"], check=True)
            written = sorted(w["path"] for w in extract_code_blocks_and_write(tmp, out))
            # a.py and b.py recovered; the truncated c.py dropped
            self.assertEqual(written, ["a.py", "b.py"])
            self.assertFalse((Path(tmp) / "c.py").exists())
