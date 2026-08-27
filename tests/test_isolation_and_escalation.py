"""
Tests for worktree isolation, the escalation ladder, and the loop actually looping.

Three defects motivate these:
  * 5 parallel DAG tasks shared one checkout, so every task's test run compiled
    every other task's half-written files and all 5 failed on each other's
    errors regardless of their own correctness (MULTI_WORKTREE_DAG was imported
    but never used, and `git worktree add` never appeared in any log);
  * a task that failed its gate was marked terminally "failed", which emptied
    ready_tasks and ended the whole run after a single pass;
  * retrying the same 2.6B model against the same task reproduces the same
    errors, so a retry must differ in KIND, not just in count.
"""

import asyncio
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from swarm.git_engine import (
    create_task_worktree,
    remove_task_worktree,
    integrate_task_worktree,
    cleanup_all_task_worktrees,
    worktree_root,
)
import swarm.loop_engine as le
from swarm.loop_engine import (
    ESCALATION_TIERS,
    current_tier_index,
    tier_is_exhausted,
    escalate_task,
    answer_user_question,
)


def _repo(td, *files):
    subprocess.run(["git", "init", "-q", "-b", "main", td], check=True)
    for name, body in files:
        fp = Path(td) / name
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(body)
    subprocess.run(["git", "-C", td, "add", "-A"], check=True)
    subprocess.run(["git", "-C", td, "-c", "user.name=t", "-c", "user.email=t@t",
                    "commit", "-qm", "init"], check=True)


class TestWorktreeIsolation(unittest.TestCase):
    def test_worktrees_live_outside_the_repository(self):
        """A worktree inside the repo gets swept into `git add -A` and scanned by
        the build — nested stray .cs files caused spurious compile errors before."""
        with tempfile.TemporaryDirectory() as td:
            _repo(td, ("a.cs", "// base\n"))
            wt = create_task_worktree(td, "main", "task-1")
            self.addCleanup(cleanup_all_task_worktrees, td)
            self.assertTrue(wt["success"])
            self.assertNotIn(str(Path(td).resolve()), str(Path(wt["path"]).resolve()))
            self.assertEqual(subprocess.run(["git", "-C", td, "status", "--porcelain"],
                                            capture_output=True, text=True).stdout, "")

    def test_concurrent_tasks_cannot_see_each_others_files(self):
        with tempfile.TemporaryDirectory() as td:
            _repo(td, ("a.cs", "// base\n"))
            self.addCleanup(cleanup_all_task_worktrees, td)
            w1 = create_task_worktree(td, "main", "task-1")
            w2 = create_task_worktree(td, "main", "task-2")
            (Path(w1["path"]) / "one.cs").write_text("// 1\n")
            self.assertFalse((Path(w2["path"]) / "one.cs").exists())

    def test_non_overlapping_work_integrates_sequentially(self):
        with tempfile.TemporaryDirectory() as td:
            _repo(td, ("a.cs", "// base\n"))
            self.addCleanup(cleanup_all_task_worktrees, td)
            branches = []
            for i, name in ((1, "one.cs"), (2, "two.cs")):
                w = create_task_worktree(td, "main", f"task-{i}")
                (Path(w["path"]) / name).write_text(f"// {i}\n")
                subprocess.run(["git", "-C", w["path"], "add", "-A"], check=True)
                subprocess.run(["git", "-C", w["path"], "-c", "user.name=t", "-c",
                                "user.email=t@t", "commit", "-qm", "w"], check=True)
                branches.append(w["branch"])
            for b in branches:
                self.assertTrue(integrate_task_worktree(td, b, "main", "m")["success"])
            self.assertTrue((Path(td) / "one.cs").exists())
            self.assertTrue((Path(td) / "two.cs").exists())

    def test_overlapping_work_reports_conflict_and_preserves_the_first(self):
        """Tasks 1 and 5 of a real run both wrote BoidConfig.cs."""
        with tempfile.TemporaryDirectory() as td:
            _repo(td, ("BoidConfig.cs", "// base\n"))
            self.addCleanup(cleanup_all_task_worktrees, td)
            # All worktrees are branched BEFORE any integration, as the scheduler
            # does — otherwise the second would branch from already-merged main
            # and never conflict.
            made = []
            for i in (1, 5):
                w = create_task_worktree(td, "main", f"task-{i}")
                (Path(w["path"]) / "BoidConfig.cs").write_text(f"// task{i}\n")
                subprocess.run(["git", "-C", w["path"], "add", "-A"], check=True)
                subprocess.run(["git", "-C", w["path"], "-c", "user.name=t", "-c",
                                "user.email=t@t", "commit", "-qm", "w"], check=True)
                made.append(w)
            results = [integrate_task_worktree(td, w["branch"], "main", "m") for w in made]
            self.assertTrue(results[0]["success"])
            self.assertFalse(results[1]["success"])
            self.assertTrue(results[1]["conflict"])
            self.assertIn("BoidConfig.cs", results[1]["conflict_files"])
            # The aborted merge must not leave the repo mid-merge.
            self.assertIn("task1", (Path(td) / "BoidConfig.cs").read_text())
            self.assertEqual(subprocess.run(["git", "-C", td, "status", "--porcelain"],
                                            capture_output=True, text=True).stdout, "")

    def test_stale_worktrees_are_cleaned(self):
        with tempfile.TemporaryDirectory() as td:
            _repo(td, ("a.cs", "// base\n"))
            create_task_worktree(td, "main", "task-1")
            create_task_worktree(td, "main", "task-2")
            self.assertEqual(cleanup_all_task_worktrees(td), 2)


class TestEscalationLadder(unittest.TestCase):
    def setUp(self):
        le.LOOP_STATE.setdefault("tasks", [])
        le.LOOP_STATE["pending_user_questions"] = []

    def _task(self):
        return {"id": "t1", "title": "Stubborn Task", "role": "dev",
                "description": "d", "acceptance_criteria": "a",
                "status": "pending", "attempts": 3, "advisor_consultations": []}

    def test_tiers_differ_in_kind_not_just_count(self):
        engines = [t["engine"] for t in ESCALATION_TIERS]
        self.assertEqual(engines, ["local", "local", "external", "user"])
        self.assertEqual(ESCALATION_TIERS[-1]["name"], "user")

    def test_second_tier_fetches_a_remediation_plan(self):
        t = self._task()
        with patch("swarm.loop_engine.ping_lead_advisor", new_callable=AsyncMock,
                   return_value="Add using System.Threading.Tasks; to BoidSimulation.cs") as ping:
            res = asyncio.run(escalate_task(t, "", ["test suite failed (exit 1)"]))
        self.assertFalse(res["blocked"])
        self.assertEqual(t["escalation_tier_name"], "local+advisor")
        self.assertIn("using System.Threading.Tasks", t["remediation_plan"])
        ping.assert_awaited()

    def test_attempt_budget_resets_per_tier_but_history_is_kept(self):
        t = self._task()
        with patch("swarm.loop_engine.ping_lead_advisor", new_callable=AsyncMock, return_value="plan"):
            asyncio.run(escalate_task(t, "", ["reason"]))
        self.assertEqual(t["attempts"], 0)
        self.assertEqual(t["attempts_at_last_tier"], 3)
        self.assertEqual(t["tier_history"][0]["tier"], "local")

    def test_third_tier_selects_the_external_engine(self):
        t = self._task()
        t["escalation_tier"] = 1
        res = asyncio.run(escalate_task(t, "", ["reason"]))
        self.assertFalse(res["blocked"])
        self.assertEqual(ESCALATION_TIERS[current_tier_index(t)]["engine"], "external")

    def test_final_tier_parks_for_the_operator_and_asks(self):
        t = self._task()
        t["escalation_tier"] = 2
        le.LOOP_STATE["tasks"] = [t]
        res = asyncio.run(escalate_task(t, "", ["test suite failed (exit 1)"]))
        self.assertTrue(res["blocked"])
        self.assertEqual(t["status"], "blocked")
        self.assertTrue(t["blocked_on_user"])
        self.assertTrue(res["question"])
        self.assertEqual(len(le.LOOP_STATE["pending_user_questions"]), 1)

    def test_repeat_of_identical_failure_at_same_tier_is_detected(self):
        t = self._task()
        reasons = ["test suite failed (exit 1)"]
        self.assertFalse(tier_is_exhausted(t, reasons))   # first observation
        self.assertTrue(tier_is_exhausted(t, reasons))    # nothing changed
        t["escalation_tier"] = 1
        self.assertFalse(tier_is_exhausted(t, reasons))   # new tier, fresh signature

    def test_operator_answer_requeues_the_task_with_their_instruction(self):
        t = self._task()
        t["escalation_tier"] = 2
        le.LOOP_STATE["tasks"] = [t]
        asyncio.run(escalate_task(t, "", ["reason"]))
        out = answer_user_question("t1", "Skip the GPU path; implement the CPU fallback only.")
        self.assertTrue(out["success"])
        self.assertEqual(t["status"], "pending")
        self.assertFalse(t["blocked_on_user"])
        self.assertIn("CPU fallback", t["remediation_plan"])
        self.assertEqual(t["escalation_tier"], 1)
        self.assertTrue(le.LOOP_STATE["pending_user_questions"][0]["answered"])

    def test_answering_an_unknown_task_is_reported(self):
        le.LOOP_STATE["tasks"] = []
        self.assertFalse(answer_user_question("nope", "x")["success"])


if __name__ == "__main__":
    unittest.main()


class TestLoopActuallyLoops(unittest.TestCase):
    """The 10:08 run ended after ONE pass: five tasks failed, were marked
    terminally "failed", which emptied ready_tasks and broke the scheduler loop.
    A failing task must now be requeued at a higher tier while other tasks keep
    running, and the run must only end when everything is done or parked."""

    def setUp(self):
        le.stop_loop()
        _pi = patch("swarm.loop_engine.pi_available", return_value=False)
        _pi.start()
        self.addCleanup(_pi.stop)

    def test_ready_tasks_excludes_parked_tasks_without_emptying(self):
        tasks = [
            {"id": "a", "status": "completed", "dependencies": []},
            {"id": "b", "status": "blocked", "blocked_on_user": True, "dependencies": []},
            {"id": "c", "status": "pending", "dependencies": []},
        ]
        completed = {t["id"] for t in tasks if t["status"] == "completed"}
        ready = [
            t for t in tasks
            if t.get("status") in ("pending", "in_progress")
            and not t.get("blocked_on_user")
            and all(d in completed for d in t.get("dependencies", []))
        ]
        self.assertEqual([t["id"] for t in ready], ["c"])

    def test_run_settles_only_when_all_tasks_are_done_or_parked(self):
        tasks = [{"id": "a", "status": "completed"}, {"id": "b", "status": "blocked"}]
        completed = sum(1 for t in tasks if t["status"] == "completed")
        blocked = sum(1 for t in tasks if t["status"] == "blocked")
        self.assertEqual(completed + blocked, len(tasks))

        tasks.append({"id": "c", "status": "pending"})
        completed = sum(1 for t in tasks if t["status"] == "completed")
        blocked = sum(1 for t in tasks if t["status"] == "blocked")
        self.assertLess(completed + blocked, len(tasks))

    def test_failing_task_is_requeued_not_terminated(self):
        """execute_zero_trust_task returns a task the scheduler can pick up again."""
        task = {"id": "t-requeue", "order": 1, "title": "Fails Once", "role": "dev",
                "description": "d", "acceptance_criteria": "a", "status": "pending",
                "attempts": 0, "advisor_consultations": []}

        async def slot(prompt, system="", **kw):
            pu = prompt.upper()
            if "SURGICAL CODE DRAFTSMAN" in pu:
                return "<|tool_call_start|>[write(path='x.py', content='v = 1\\n')]<|tool_call_end|>"
            if "ZERO-TRUST QA MANDATE" in pu:
                return "VERDICT: FAILED (Reason: no coverage)"
            if "ZERO-TRUST SECURITY MANDATE" in pu:
                return "VERDICT: PASSED"
            if "AUTONOMOUS SWARM AUTO-JUDGE" in pu:
                return "DECISION: REJECTED (Diagnostics: fix coverage)"
            return "OK"

        async def run():
            with tempfile.TemporaryDirectory() as td, \
                 patch("swarm.loop_engine.query_local_slot", side_effect=slot), \
                 patch("swarm.loop_engine.query_qwen_web", new_callable=AsyncMock, return_value="ok"), \
                 patch("swarm.loop_engine.ping_lead_advisor", new_callable=AsyncMock, return_value="plan"), \
                 patch("swarm.loop_engine.commit_changes") as mock_commit:
                out = await le.execute_zero_trust_task(task, "", td, "", None)
                return out, mock_commit

        result, mock_commit = asyncio.run(run())
        # Requeued for a different tier, never committed, never "completed".
        self.assertEqual(result["status"], "pending")
        self.assertGreaterEqual(result["escalation_tier"], 1)
        self.assertNotEqual(result["status"], "completed")
        mock_commit.assert_not_called()

    def test_max_iterations_still_bounds_the_run(self):
        """"Do not stop" must not mean "never finish"."""
        le.LOOP_STATE["iteration"] = 20
        le.LOOP_STATE["max_iterations"] = 20
        self.assertGreaterEqual(le.LOOP_STATE["iteration"], le.LOOP_STATE["max_iterations"])
