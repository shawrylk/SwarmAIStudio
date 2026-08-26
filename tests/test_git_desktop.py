"""
Unit Tests for GitHub Desktop Experience & Git Engine in Swarm AI Studio
"""

import unittest
import tempfile
import shutil
import subprocess
from pathlib import Path

from swarm.git_engine import (
    run_git,
    git_status_detailed,
    git_stage_files,
    git_unstage_files,
    git_discard_changes,
    git_commit_staged,
    git_fetch_remote,
    git_pull_remote,
    git_push_remote,
    git_list_branches_detailed,
    git_checkout_branch,
    git_delete_branch,
    git_merge_branch_into_current,
    git_commit_history_detailed,
    git_commit_diff,
    git_file_diff,
    git_stash_ops,
    git_revert_commit,
    git_reset_commit,
    gh_issue_reopen,
    get_full_github_desktop_state
)

class TestGitDesktopEngine(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="test_swarm_git_")
        self.repo_path = self.test_dir
        
        # Initialize test git repo
        subprocess.run(["git", "init", "-b", "main", self.repo_path], check=True, capture_output=True)
        subprocess.run(["git", "-C", self.repo_path, "config", "user.name", "Test User"], check=True)
        subprocess.run(["git", "-C", self.repo_path, "config", "user.email", "test@user.com"], check=True)
        
        # Create initial commit
        init_file = Path(self.repo_path) / "README.md"
        init_file.write_text("# Test Repo\nInitial content\n")
        subprocess.run(["git", "-C", self.repo_path, "add", "README.md"], check=True)
        subprocess.run(["git", "-C", self.repo_path, "commit", "-m", "Initial commit"], check=True)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_git_status_detailed_and_staging(self):
        # 1. Initially clean
        status = git_status_detailed(self.repo_path)
        self.assertTrue(status["clean"])
        self.assertEqual(len(status["staged"]), 0)
        self.assertEqual(len(status["unstaged"]), 0)
        self.assertEqual(len(status["untracked"]), 0)
        self.assertEqual(status["current_branch"], "main")

        # 2. Add modified file and untracked file
        readme = Path(self.repo_path) / "README.md"
        readme.write_text("# Test Repo\nModified line\n")
        new_file = Path(self.repo_path) / "feature.py"
        new_file.write_text("print('hello')\n")

        status2 = git_status_detailed(self.repo_path)
        self.assertFalse(status2["clean"])
        self.assertEqual(len(status2["unstaged"]), 1)
        self.assertEqual(status2["unstaged"][0]["path"], "README.md")
        self.assertEqual(len(status2["untracked"]), 1)
        self.assertEqual(status2["untracked"][0]["path"], "feature.py")

        # 3. Stage feature.py
        stage_res = git_stage_files(self.repo_path, ["feature.py"])
        self.assertTrue(stage_res["success"])
        
        status3 = git_status_detailed(self.repo_path)
        self.assertEqual(len(status3["staged"]), 1)
        self.assertEqual(status3["staged"][0]["path"], "feature.py")
        self.assertEqual(len(status3["unstaged"]), 1)

        # 4. Unstage feature.py
        unstage_res = git_unstage_files(self.repo_path, ["feature.py"])
        self.assertTrue(unstage_res["success"])
        status4 = git_status_detailed(self.repo_path)
        self.assertEqual(len(status4["staged"]), 0)

        # 5. Discard changes to README.md
        discard_res = git_discard_changes(self.repo_path, ["README.md"])
        self.assertTrue(discard_res["success"])
        self.assertEqual(readme.read_text(), "# Test Repo\nInitial content\n")

        # 6. Discard untracked feature.py
        discard_untracked = git_discard_changes(self.repo_path, ["feature.py"])
        self.assertTrue(discard_untracked["success"])
        self.assertFalse(new_file.exists())

    def test_git_commit_staged(self):
        code_file = Path(self.repo_path) / "app.py"
        code_file.write_text("def run(): pass\n")
        git_stage_files(self.repo_path, ["app.py"])

        res = git_commit_staged(self.repo_path, "feat: Add app.py", "Detailed commit description")
        self.assertTrue(res["success"])
        self.assertTrue(res["committed"])
        self.assertEqual(res["summary"], "feat: Add app.py")
        self.assertIn("Detailed commit description", res["message"])
        self.assertTrue(len(res["short_hash"]) >= 7)

        # Verify commit in history
        history = git_commit_history_detailed(self.repo_path, limit=5)
        self.assertGreaterEqual(len(history), 2)
        self.assertEqual(history[0]["subject"], "feat: Add app.py")

    def test_git_branch_operations_and_merge(self):
        # 1. Create and checkout new branch
        b_res = git_checkout_branch(self.repo_path, "feature-auth", create_if_missing=True)
        self.assertTrue(b_res["success"])

        branches = git_list_branches_detailed(self.repo_path)
        names = [b["name"] for b in branches]
        self.assertIn("feature-auth", names)
        
        # 2. Add commit on feature branch
        f = Path(self.repo_path) / "auth.py"
        f.write_text("TOKEN = 'secret'\n")
        git_stage_files(self.repo_path, ["auth.py"])
        git_commit_staged(self.repo_path, "feat(auth): add auth token")

        # 3. Checkout main
        checkout_main = git_checkout_branch(self.repo_path, "main")
        self.assertTrue(checkout_main["success"])

        # 4. Merge feature-auth into main
        merge_res = git_merge_branch_into_current(self.repo_path, "feature-auth", message="Merge feature-auth")
        self.assertTrue(merge_res["success"])
        self.assertTrue(merge_res["merged"])
        self.assertTrue((Path(self.repo_path) / "auth.py").exists())

        # 5. Delete branch
        del_res = git_delete_branch(self.repo_path, "feature-auth", force=True)
        self.assertTrue(del_res["success"])

    def test_git_stash_operations(self):
        # Make a dirty change
        readme = Path(self.repo_path) / "README.md"
        readme.write_text("# WIP Stash Test\n")

        # Save stash via dispatcher
        save_res = git_stash_ops(self.repo_path, "save", message="WIP Test")
        self.assertTrue(save_res["success"])

        # List stashes
        list_res = git_stash_ops(self.repo_path, "list")
        self.assertTrue(list_res["success"])
        self.assertGreaterEqual(len(list_res["stashes"]), 1)
        self.assertIn("WIP Test", list_res["stashes"][0]["message"])

        # Pop stash
        pop_res = git_stash_ops(self.repo_path, "pop", index=0)
        self.assertTrue(pop_res["success"])
        self.assertEqual(readme.read_text(), "# WIP Stash Test\n")

    def test_git_diff_and_commit_detail(self):
        f = Path(self.repo_path) / "diff_test.txt"
        f.write_text("Line 1\nLine 2\n")
        git_stage_files(self.repo_path, ["diff_test.txt"])
        git_commit_staged(self.repo_path, "init diff_test")

        # Modify file
        f.write_text("Line 1\nLine 2 modified\nLine 3 added\n")
        diff_text = git_file_diff(self.repo_path, "diff_test.txt", staged=False)
        self.assertIn("+Line 2 modified", diff_text)
        self.assertIn("-Line 2", diff_text)

        # Commit and get commit diff
        git_stage_files(self.repo_path, ["diff_test.txt"])
        c_res = git_commit_staged(self.repo_path, "update diff_test")
        c_diff = git_commit_diff(self.repo_path, c_res["commit_hash"])
        self.assertEqual(c_diff["hash"], c_res["commit_hash"])
        self.assertIn("diff_test.txt", c_diff["files"])

    def test_get_full_github_desktop_state(self):
        state = get_full_github_desktop_state(self.repo_path)
        self.assertTrue(state["active"])
        self.assertEqual(state["branch"], "main")
        self.assertIn("staged", state)
        self.assertIn("unstaged", state)
        self.assertIn("untracked", state)
        self.assertIn("history", state)
        self.assertIn("branches", state)
        self.assertIn("stashes", state)
        self.assertIn("worktrees", state)

    def test_git_revert_and_reset(self):
        f = Path(self.repo_path) / "temp.txt"
        f.write_text("v1\n")
        git_stage_files(self.repo_path, ["temp.txt"])
        c1 = git_commit_staged(self.repo_path, "commit 1")

        f.write_text("v2\n")
        git_stage_files(self.repo_path, ["temp.txt"])
        c2 = git_commit_staged(self.repo_path, "commit 2")

        # Revert c2
        rev_res = git_revert_commit(self.repo_path, c2["commit_hash"])
        self.assertTrue(rev_res["success"])
        self.assertEqual(f.read_text(), "v1\n")

        # Reset to c1
        reset_res = git_reset_commit(self.repo_path, c1["commit_hash"], mode="hard")
        self.assertTrue(reset_res["success"])
        curr_head = run_git(self.repo_path, ["rev-parse", "HEAD"])["stdout"]
        self.assertEqual(curr_head, c1["commit_hash"])


import json
import threading
from http.server import HTTPServer
import urllib.request
from swarm.server import SwarmHandler

class TestGitDesktopServerEndpoints(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = HTTPServer(('127.0.0.1', 0), SwarmHandler)
        cls.port = cls.httpd.server_address[1]
        cls.server_thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.server_thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="test_swarm_srv_git_")
        self.repo_path = self.test_dir
        subprocess.run(["git", "init", "-b", "main", self.repo_path], check=True, capture_output=True)
        subprocess.run(["git", "-C", self.repo_path, "config", "user.name", "Test Server"], check=True)
        subprocess.run(["git", "-C", self.repo_path, "config", "user.email", "server@test.com"], check=True)
        init_file = Path(self.repo_path) / "init.txt"
        init_file.write_text("server init\n")
        subprocess.run(["git", "-C", self.repo_path, "add", "init.txt"], check=True)
        subprocess.run(["git", "-C", self.repo_path, "commit", "-m", "Initial commit"], check=True)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def _get(self, path):
        url = f"http://127.0.0.1:{self.port}{path}"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode('utf-8'))

    def _post(self, path, payload):
        url = f"http://127.0.0.1:{self.port}{path}"
        data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode('utf-8'))

    def test_http_git_overview_and_status(self):
        overview = self._get(f"/api/git/overview?repo_path={self.repo_path}")
        self.assertTrue(overview["active"])
        self.assertEqual(overview["branch"], "main")

        status = self._get(f"/api/git/status?repo_path={self.repo_path}")
        self.assertTrue(status["clean"])

    def test_http_stage_unstage_commit_discard(self):
        # 1. Modify file and create new file
        f = Path(self.repo_path) / "test.py"
        f.write_text("a = 1\n")

        # 2. Stage file via HTTP
        stage_res = self._post("/api/git/stage", {"repo_path": self.repo_path, "files": ["test.py"]})
        self.assertTrue(stage_res["success"])

        # Check status
        st = self._get(f"/api/git/status?repo_path={self.repo_path}")
        self.assertEqual(len(st["staged"]), 1)

        # 3. Commit via HTTP
        commit_res = self._post("/api/git/commit", {
            "repo_path": self.repo_path,
            "summary": "feat: add test.py",
            "description": "via HTTP POST test"
        })
        self.assertTrue(commit_res["success"])
        self.assertTrue(commit_res["committed"])

        # 4. Modify and discard via HTTP
        f.write_text("a = 2\n")
        discard_res = self._post("/api/git/discard", {"repo_path": self.repo_path, "files": ["test.py"]})
        self.assertTrue(discard_res["success"])
        self.assertEqual(f.read_text(), "a = 1\n")

    def test_http_branch_and_history_operations(self):
        # 1. Create and checkout branch via HTTP
        br_res = self._post("/api/git/branch/checkout", {
            "repo_path": self.repo_path,
            "branch": "feature/api-v2",
            "create": True
        })
        self.assertTrue(br_res["success"])

        branches = self._get(f"/api/git/branches?repo_path={self.repo_path}")
        b_names = [b["name"] for b in branches["branches"]]
        self.assertIn("feature/api-v2", b_names)

        # 2. Commit on new branch
        f2 = Path(self.repo_path) / "v2.py"
        f2.write_text("print('v2')\n")
        self._post("/api/git/stage", {"repo_path": self.repo_path, "files": ["v2.py"]})
        c_res = self._post("/api/git/commit", {"repo_path": self.repo_path, "summary": "feat: v2"})
        self.assertTrue(c_res["success"])

        # 3. Switch back to main and merge
        self._post("/api/git/branch/checkout", {"repo_path": self.repo_path, "branch": "main"})
        merge_res = self._post("/api/git/branch/merge", {
            "repo_path": self.repo_path,
            "source_branch": "feature/api-v2"
        })
        self.assertTrue(merge_res["success"])
        self.assertTrue(merge_res["merged"])

        # 4. Get history via HTTP
        history = self._get(f"/api/git/history?repo_path={self.repo_path}")
        self.assertGreaterEqual(len(history["history"]), 2)

if __name__ == "__main__":
    unittest.main()

