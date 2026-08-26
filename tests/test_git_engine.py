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

    def test_github_issue_and_pr_integration(self):
        from unittest.mock import patch, MagicMock
        import subprocess
        from swarm.git_engine import (
            is_gh_available,
            gh_issue_create,
            gh_issue_comment,
            gh_issue_close,
            gh_issue_list,
            gh_pr_create
        )
        self.assertTrue(is_gh_available())
        
        # Test 1: Successful gh CLI execution
        mock_proc_create = MagicMock(returncode=0, stdout="https://github.com/owner/repo/issues/42\n", stderr="")
        mock_proc_comment = MagicMock(returncode=0, stdout="", stderr="")
        mock_proc_close = MagicMock(returncode=0, stdout="", stderr="")
        mock_proc_list = MagicMock(returncode=0, stdout='[{"number": 42, "title": "Test Goal", "state": "open", "url": "https://github.com/owner/repo/issues/42"}]', stderr="")
        mock_proc_pr = MagicMock(returncode=0, stdout="https://github.com/owner/repo/pull/7\n", stderr="")

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = mock_proc_create
            issue_res = gh_issue_create("/fake/repo", "Test Goal", "Body", labels=["swarm", "automated"])
            self.assertTrue(issue_res["success"])
            self.assertEqual(issue_res["issue_number"], 42)
            self.assertFalse(issue_res["fallback"])

            mock_run.return_value = mock_proc_comment
            comment_res = gh_issue_comment("/fake/repo", 42, "Dev drafted code")
            self.assertTrue(comment_res["success"])
            self.assertFalse(comment_res["fallback"])

            mock_run.return_value = mock_proc_close
            close_res = gh_issue_close("/fake/repo", 42, "All tests passed", reason="completed")
            self.assertTrue(close_res["success"])
            self.assertFalse(close_res["fallback"])

            mock_run.return_value = mock_proc_list
            list_res = gh_issue_list("/fake/repo")
            self.assertTrue(list_res["success"])
            self.assertEqual(len(list_res["issues"]), 1)
            self.assertEqual(list_res["issues"][0]["number"], 42)

            mock_run.return_value = mock_proc_pr
            pr_res = gh_pr_create("/fake/repo", "Feature PR", "PR description")
            self.assertTrue(pr_res["success"])
            self.assertEqual(pr_res["pr_number"], 7)

        # Test 2: Fallback path when gh fails or raises exception
        with patch("subprocess.run", side_effect=Exception("Network unreachable")):
            fb_issue = gh_issue_create("/fake/repo", "Offline Goal", "Offline Body")
            self.assertTrue(fb_issue["success"])
            self.assertTrue(fb_issue["fallback"])
            self.assertIn("local://issue/", fb_issue["url"])

            fb_comment = gh_issue_comment("/fake/repo", fb_issue["issue_number"], "Offline comment")
            self.assertTrue(fb_comment["success"])
            self.assertTrue(fb_comment["fallback"])

            fb_close = gh_issue_close("/fake/repo", fb_issue["issue_number"], "Offline close")
            self.assertTrue(fb_close["success"])
            self.assertTrue(fb_close["fallback"])

    def test_extract_code_blocks_and_write_markdown(self):
        import tempfile
        from swarm.git_engine import extract_code_blocks_and_write
        
        with tempfile.TemporaryDirectory() as tmpdir:
            llm_text = """Here is the implementation:

```python filepath=src/calculator.py
def add(a: int, b: int) -> int:
    return a + b
```

### `tests/test_calculator.py`
```python
import unittest
from src.calculator import add

class TestCalc(unittest.TestCase):
    def test_add(self):
        self.assertEqual(add(2, 3), 5)
```
"""
            written = extract_code_blocks_and_write(tmpdir, llm_text)
            self.assertEqual(len(written), 2)
            
            calc_p = Path(tmpdir) / "src" / "calculator.py"
            test_p = Path(tmpdir) / "tests" / "test_calculator.py"
            
            self.assertTrue(calc_p.exists())
            self.assertTrue(test_p.exists())
            self.assertIn("def add(a: int, b: int)", calc_p.read_text())
            self.assertIn("class TestCalc", test_p.read_text())

    def test_extract_code_blocks_and_write_json_format(self):
        import tempfile
        from swarm.git_engine import extract_code_blocks_and_write

        with tempfile.TemporaryDirectory() as tmpdir:
            json_text = """```json
[
  {"path": "config/settings.json", "content": "{\\"debug\\": true}"},
  {"path": "src/logger.py", "content": "def log(msg): print(msg)"}
]
```"""
            written = extract_code_blocks_and_write(tmpdir, json_text)
            self.assertEqual(len(written), 2)
            
            cfg_p = Path(tmpdir) / "config" / "settings.json"
            log_p = Path(tmpdir) / "src" / "logger.py"
            
            self.assertTrue(cfg_p.exists())
            self.assertTrue(log_p.exists())
            self.assertIn("debug", cfg_p.read_text())

    def test_detect_project_test_runner(self):
        import tempfile
        from swarm.git_engine import detect_project_test_runner

        with tempfile.TemporaryDirectory() as tmpdir:
            # Python project with tests/
            t_dir = Path(tmpdir) / "tests"
            t_dir.mkdir()
            (t_dir / "test_sample.py").write_text("def test_ok(): pass")
            
            runner = detect_project_test_runner(tmpdir)
            self.assertIsNotNone(runner)
            self.assertIn(runner["runner"], ["pytest", "python_unittest"])

            # Node project
            with tempfile.TemporaryDirectory() as node_tmp:
                (Path(node_tmp) / "package.json").write_text('{"scripts": {"test": "jest"}}')
                n_runner = detect_project_test_runner(node_tmp)
                self.assertIsNotNone(n_runner)
                self.assertEqual(n_runner["runner"], "npm")

    def test_run_test_suite_execution(self):
        import tempfile
        from swarm.git_engine import run_test_suite

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a passing unittest
            t_dir = Path(tmpdir) / "tests"
            t_dir.mkdir()
            (t_dir / "test_pass.py").write_text("""
import unittest
class SampleTest(unittest.TestCase):
    def test_simple(self):
        self.assertEqual(1 + 1, 2)
if __name__ == '__main__':
    unittest.main()
""")
            res = run_test_suite(tmpdir, custom_cmd=["python3", "-m", "unittest", "discover", "tests"])
            self.assertTrue(res["success"])
            self.assertEqual(res["exit_code"], 0)

            # Create a failing unittest
            (t_dir / "test_fail.py").write_text("""
import unittest
class FailTest(unittest.TestCase):
    def test_failure(self):
        self.assertEqual(1 + 1, 99)
""")
            res_fail = run_test_suite(tmpdir, custom_cmd=["python3", "-m", "unittest", "discover", "tests"])
            self.assertFalse(res_fail["success"])
            self.assertNotEqual(res_fail["exit_code"], 0)
            self.assertIn("AssertionError", res_fail["output"])

    def test_git_diff_commit_and_merge_lifecycle(self):
        import tempfile
        import subprocess
        from swarm.git_engine import (
            get_working_diff,
            commit_changes,
            merge_branch,
            switch_or_create_branch
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            # 1. Initialize git repo
            subprocess.run(["git", "-C", tmpdir, "init", "-b", "main"], check=True, capture_output=True)
            subprocess.run(["git", "-C", tmpdir, "config", "user.name", "Test User"], check=True)
            subprocess.run(["git", "-C", tmpdir, "config", "user.email", "test@user.com"], check=True)

            # Initial commit on main
            readme = Path(tmpdir) / "README.md"
            readme.write_text("# Main Project")
            commit_changes(tmpdir, "Initial commit on main")

            # 2. Create and switch to isolated branch
            branch_name = "swarm/task-1"
            switch_or_create_branch(tmpdir, branch_name, create=True)

            # 3. Create real code files
            code_file = Path(tmpdir) / "app.py"
            code_file.write_text("print('Hello Swarm')\n")

            # 4. Check working diff
            diff_text = get_working_diff(tmpdir)
            self.assertIn("Hello Swarm", diff_text)

            # 5. Commit changes on branch
            commit_res = commit_changes(tmpdir, "feat(dev): Add app.py [Swarm Task #task-1]")
            self.assertTrue(commit_res["success"])
            self.assertTrue(commit_res["committed"])
            self.assertTrue(len(commit_res["commit_hash"]) > 0)

            # 6. Merge branch into main
            merge_res = merge_branch(tmpdir, source_branch=branch_name, target_branch="main", message="Merge swarm/task-1 into main")
            self.assertTrue(merge_res["success"])
            self.assertTrue(merge_res["merged"])
            self.assertEqual(merge_res["target_branch"], "main")
            
            # Verify code exists on main
            self.assertTrue((Path(tmpdir) / "app.py").exists())
            self.assertIn("Hello Swarm", (Path(tmpdir) / "app.py").read_text())

if __name__ == "__main__":
    unittest.main()



