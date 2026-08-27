"""
Comprehensive Test Suite for Autonomous Swarm Loop:
1. Complete Happy Path (End-to-End Verification, Code Production, Git Commit & Merge)
2. Fail Cases at every distinct stage:
   - Stage 0: Branch Checkout / Dirty Working Tree Failure
   - Stage 1: Dev Drafting / No-Write Failure
   - Stage 2: QA / Real Test Suite Execution Failure
   - Stage 2b: Host Infrastructure / Dependency Broken Failure
   - Stage 3: Security Threat Audit Failure
   - Stage 4: Adversarial Oracle & Contract Invariant Failure
   - Stage 5: Auto-Judge Gate Decision Rejection
   - Stage 6: Final Merge Honesty Gate (Empty Deliverable / 0 Files Written)
   - Stage 7: DAG Deadlock / Stalled Dependency Failure
"""

import asyncio
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, AsyncMock, MagicMock

import swarm.loop_engine as le
from swarm.loop_engine import (
    start_loop,
    stop_loop,
    get_loop_state,
    execute_zero_trust_task,
    _async_loop_runner,
)
from swarm.sessions import create_new_loop_session, load_loop_session, delete_loop_session


class TestLoopHappyPathAndStageFailures(unittest.TestCase):
    def setUp(self):
        stop_loop()
        # The dev stage defaults to the Pi agent, which spawns a real subprocess
        # against a live model. These tests exercise orchestration, not the agent,
        # so pin them to the single-completion path. Pi wiring is covered by
        # tests/test_pi_agent_bridge.py with run_pi_agent mocked.
        _pi = patch("swarm.loop_engine.pi_available", return_value=False)
        _pi.start()
        self.addCleanup(_pi.stop)

    def tearDown(self):
        stop_loop()

    # ─────────────────────────────────────────────────────────────
    # 1. HAPPY PATH: COMPLETE END-TO-END VERIFIED RUN
    # ─────────────────────────────────────────────────────────────
    def test_happy_path_end_to_end_completion_and_merge(self):
        """Happy Path: All stages pass, code written, tests pass, gate approved, committed, merged."""
        with tempfile.TemporaryDirectory() as td:
            repo_p = Path(td)
            subprocess.run(["git", "init", "-b", "main", str(repo_p)], capture_output=True, check=True)
            (repo_p / "README.md").write_text("# Test Project\n")
            subprocess.run(["git", "-C", str(repo_p), "add", "-A"], check=True)
            subprocess.run(["git", "-C", str(repo_p), "-c", "user.name=tester", "-c", "user.email=tester@test.com", "commit", "-m", "initial commit"], check=True)

            sess = create_new_loop_session(title="Happy Path Feature", goal="Build High Performance Cache", repo_path=str(repo_p))
            sess_id = sess["id"]

            async def mock_query_gemini(prompt, **kwargs):
                pu = prompt.upper()
                if "CHIEF RESEARCH" in pu:
                    return "# Pre-Flight Research Brief\n\nCache Architecture\n\n### 📜 Universal Contract Invariants & Schemas\nOpenAPI Cache"
                if "CHIEF PRODUCT" in pu:
                    return json.dumps([{
                        "title": "Implement Cache Store",
                        "role": "dev",
                        "description": "Construct MemoryCache class",
                        "acceptance_criteria": "100% test assertions pass",
                        "dependencies": []
                    }])
                if "LEAD ADVISOR" in pu:
                    return "Executive Summary: High Performance Cache implemented and zero-trust verified."
                return "OK"

            async def mock_query_local_slot(prompt, system="", **kwargs):
                pu = prompt.upper()
                if "SURGICAL CODE DRAFTSMAN" in pu:
                    return "<|tool_call_start|>[write(path='src/cache.py', content='class Cache:\\n    pass\\n')]<|tool_call_end|>"
                if "ZERO-TRUST QA MANDATE" in pu:
                    return "VERDICT: PASSED"
                if "ZERO-TRUST SECURITY MANDATE" in pu:
                    return "VERDICT: PASSED"
                if "AUTONOMOUS SWARM AUTO-JUDGE" in pu:
                    return "DECISION: APPROVED (Certificate: Verified clean cache)"
                return "OK"

            async def run():
                with patch("swarm.loop_engine.query_gemini", side_effect=mock_query_gemini), \
                     patch("swarm.loop_engine.query_local_slot", side_effect=mock_query_local_slot), \
                     patch("swarm.loop_engine.query_qwen_web", new_callable=AsyncMock, return_value="Verified consensus"), \
                     patch("swarm.loop_engine.ping_lead_advisor", new_callable=AsyncMock, return_value="Guidance"), \
                     patch("swarm.loop_engine.run_test_suite", return_value={"success": True, "skipped": False, "runner": "pytest", "exit_code": 0, "output": "1 passed"}), \
                     patch("swarm.loop_engine.gh_issue_create", return_value={"issue_number": 1, "url": "https://github.com/test/repo/issues/1"}), \
                     patch("swarm.loop_engine.gh_issue_close"), \
                     patch("swarm.loop_engine.gh_project_ensure", return_value={"available": False}):
                    
                    le.LOOP_STATE["id"] = sess_id
                    le.LOOP_STATE["session_id"] = sess_id
                    le.LOOP_STATE["goal"] = "Build High Performance Cache"
                    le.LOOP_STATE["repo_path"] = str(repo_p)
                    le.LOOP_STATE["status"] = "running"
                    le.LOOP_STATE["tasks"] = []
                    
                    await _async_loop_runner()

            asyncio.run(run())

            state = get_loop_state()
            self.assertEqual(state["status"], "completed")
            self.assertTrue(state.get("produced_code"))
            self.assertEqual(state.get("files_written_total"), 1)
            self.assertEqual(len(state.get("tasks", [])), 1)
            self.assertEqual(state["tasks"][0]["status"], "completed")
            self.assertIsNone(state.get("active_subagent"))
            delete_loop_session(sess_id)

    # ─────────────────────────────────────────────────────────────
    # 2. STAGE 0: DIRTY TREE / BRANCH CHECKOUT FAILURE
    # ─────────────────────────────────────────────────────────────
    def test_stage_0_branch_checkout_failure_fails_cleanly(self):
        """Stage 0: Uncommitted dirty changes block checkout -> loop fails immediately with clean status."""
        with tempfile.TemporaryDirectory() as td:
            repo_p = Path(td)
            subprocess.run(["git", "init", "-b", "main", str(repo_p)], capture_output=True, check=True)
            (repo_p / "README.md").write_text("# Base\n")
            subprocess.run(["git", "-C", str(repo_p), "add", "-A"], check=True)
            subprocess.run(["git", "-C", str(repo_p), "-c", "user.name=tester", "-c", "user.email=tester@test.com", "commit", "-m", "init"], check=True)
            subprocess.run(["git", "-C", str(repo_p), "checkout", "-b", "swarm/old-branch"], check=True)
            (repo_p / "dirty.txt").write_text("uncommitted changes")

            sess = create_new_loop_session(title="Dirty Checkout Test", goal="New Feature", repo_path=str(repo_p))
            sess_id = sess["id"]

            async def run():
                with patch("swarm.loop_engine.switch_or_create_branch", return_value={"success": False, "error": "the working tree has uncommitted changes"}), \
                     patch("swarm.loop_engine.run_git", return_value={"stdout": "swarm/old-branch", "returncode": 0}):
                    le.LOOP_STATE["id"] = sess_id
                    le.LOOP_STATE["session_id"] = sess_id
                    le.LOOP_STATE["goal"] = "New Feature"
                    le.LOOP_STATE["repo_path"] = str(repo_p)
                    le.LOOP_STATE["status"] = "running"
                    le.LOOP_STATE["tasks"] = []
                    await _async_loop_runner()

            asyncio.run(run())

            state = get_loop_state()
            self.assertEqual(state["status"], "failed")
            self.assertIn("Refusing to run", state.get("final_summary", ""))
            delete_loop_session(sess_id)

    # ─────────────────────────────────────────────────────────────
    # 3. STAGE 1: DEV DRAFTING / NO-WRITE FAILURE
    # ─────────────────────────────────────────────────────────────
    def test_stage_1_dev_no_writes_fails_gate_honesty(self):
        """Stage 1: Dev model emits only inspection calls and 0 file writes -> fails gate honesty."""
        task = {
            "id": "task-dev-fail", "order": 1, "title": "Implement Feature",
            "role": "dev", "description": "Write code", "acceptance_criteria": "pass",
            "status": "pending", "attempts": 0, "advisor_consultations": [],
        }

        async def mock_query_local_slot(prompt, system="", **kwargs):
            pu = prompt.upper()
            if "SURGICAL CODE DRAFTSMAN" in pu or "BLOCKING: NO FILES WERE WRITTEN" in pu:
                return "<|tool_call_start|>[read_file(path='src/missing.py')]<|tool_call_end|>"
            if "ZERO-TRUST QA MANDATE" in pu:
                return "VERDICT: PASSED"
            if "ZERO-TRUST SECURITY MANDATE" in pu:
                return "VERDICT: PASSED"
            if "AUTONOMOUS SWARM AUTO-JUDGE" in pu:
                return "DECISION: APPROVED"
            return "OK"

        async def run():
            with patch("swarm.loop_engine.query_local_slot", side_effect=mock_query_local_slot), \
                 patch("swarm.loop_engine.query_qwen_web", new_callable=AsyncMock, return_value="ok"), \
                 patch("swarm.loop_engine.ping_lead_advisor", new_callable=AsyncMock, return_value="g"), \
                 patch("swarm.loop_engine.commit_changes") as mock_commit:
                out = await execute_zero_trust_task(
                    task, repo_block="", repo_path="", research_brief="", github_issue_num=None
                )
                return out, mock_commit

        result, mock_commit = asyncio.run(run())
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["files_written"], [])
        self.assertIn("dev wrote no files", result.get("failure_reasons", []))
        mock_commit.assert_not_called()

    # ─────────────────────────────────────────────────────────────
    # 4. STAGE 2: QA / REAL TEST SUITE EXECUTION FAILURE
    # ─────────────────────────────────────────────────────────────
    def test_stage_2_test_suite_failure_rejects_and_fails_task(self):
        """Stage 2: Real test suite fails (exit code 1) -> QA fails, Auto-Judge rejects -> task fails."""
        task = {
            "id": "task-qa-fail", "order": 1, "title": "Failing Tests",
            "role": "dev", "description": "Write failing code", "acceptance_criteria": "pass",
            "status": "pending", "attempts": 0, "advisor_consultations": [],
        }

        async def mock_query_local_slot(prompt, system="", **kwargs):
            pu = prompt.upper()
            if "SURGICAL CODE DRAFTSMAN" in pu:
                return "<|tool_call_start|>[write(path='src/math.py', content='def add(a, b): return a - b\\n')]<|tool_call_end|>"
            if "ZERO-TRUST QA MANDATE" in pu:
                return "VERDICT: FAILED (Reason: AssertionError in test_add)"
            if "ZERO-TRUST SECURITY MANDATE" in pu:
                return "VERDICT: PASSED"
            if "AUTONOMOUS SWARM AUTO-JUDGE" in pu:
                return "DECISION: REJECTED (Diagnostics: Fix math logic)"
            return "OK"

        async def run():
            with patch("swarm.loop_engine.query_local_slot", side_effect=mock_query_local_slot), \
                 patch("swarm.loop_engine.query_qwen_web", new_callable=AsyncMock, return_value="ok"), \
                 patch("swarm.loop_engine.ping_lead_advisor", new_callable=AsyncMock, return_value="g"), \
                 patch("swarm.loop_engine.run_test_suite", return_value={"success": False, "skipped": False, "runner": "pytest", "exit_code": 1, "output": "FAILED test_add"}), \
                 patch("swarm.loop_engine.commit_changes") as mock_commit:
                out = await execute_zero_trust_task(
                    task, repo_block="", repo_path="", research_brief="", github_issue_num=None
                )
                return out, mock_commit

        result, mock_commit = asyncio.run(run())
        self.assertEqual(result["status"], "failed")
        self.assertFalse(result.get("qa_passed"))
        self.assertIn("QA verdict not PASSED", result.get("failure_reasons", []))
        mock_commit.assert_not_called()

    # ─────────────────────────────────────────────────────────────
    # 5. STAGE 2B: HOST INFRASTRUCTURE BROKEN / MISSING DEPENDENCY
    # ─────────────────────────────────────────────────────────────
    def test_stage_2b_infra_broken_withholds_pass_and_records_blocker(self):
        """Stage 2b: Host environment broken -> classified as infra blocker, deliverable unverified."""
        task = {
            "id": "task-infra-fail", "order": 1, "title": "Infra Fail",
            "role": "dev", "description": "impl", "acceptance_criteria": "pass",
            "status": "pending", "attempts": 0, "advisor_consultations": [],
        }

        async def mock_query_local_slot(prompt, system="", **kwargs):
            pu = prompt.upper()
            if "SURGICAL CODE DRAFTSMAN" in pu:
                return "<|tool_call_start|>[write(path='src/logic.py', content='x = 10\\n')]<|tool_call_end|>"
            if "ZERO-TRUST QA MANDATE" in pu:
                return "VERDICT: FAILED (Reason: UNVERIFIED — test infrastructure failure)"
            if "ZERO-TRUST SECURITY MANDATE" in pu:
                return "VERDICT: PASSED"
            if "AUTONOMOUS SWARM AUTO-JUDGE" in pu:
                return "DECISION: REJECTED (Diagnostics: Host environment broken)"
            return "OK"

        async def run():
            with patch("swarm.loop_engine.query_local_slot", side_effect=mock_query_local_slot), \
                 patch("swarm.loop_engine.query_qwen_web", new_callable=AsyncMock, return_value="ok"), \
                 patch("swarm.loop_engine.ping_lead_advisor", new_callable=AsyncMock, return_value="g"), \
                 patch("swarm.loop_engine.run_test_suite", return_value={"success": False, "skipped": False, "runner": "pytest", "exit_code": 127, "output": "bash: pytest: command not found", "missing_dependency": "pytest"}), \
                 patch("swarm.loop_engine.commit_changes") as mock_commit:
                out = await execute_zero_trust_task(
                    task, repo_block="", repo_path="", research_brief="", github_issue_num=None
                )
                return out, mock_commit

        result, mock_commit = asyncio.run(run())
        self.assertEqual(result["status"], "failed")
        self.assertFalse(result.get("qa_passed"))
        self.assertTrue(any("infrastructure" in r for r in result.get("failure_reasons", [])))
        mock_commit.assert_not_called()

    # ─────────────────────────────────────────────────────────────
    # 6. STAGE 3: SECURITY THREAT AUDIT FAILURE
    # ─────────────────────────────────────────────────────────────
    def test_stage_3_security_vulnerability_rejects_task(self):
        """Stage 3: Security Auditor detects SQL injection -> Auto-Judge rejects -> task fails."""
        task = {
            "id": "task-sec-fail", "order": 1, "title": "SQL Query Endpoint",
            "role": "dev", "description": "Write query", "acceptance_criteria": "pass",
            "status": "pending", "attempts": 0, "advisor_consultations": [],
        }

        async def mock_query_local_slot(prompt, system="", **kwargs):
            pu = prompt.upper()
            if "SURGICAL CODE DRAFTSMAN" in pu:
                return "<|tool_call_start|>[write(path='src/db.py', content='def get_user(name): db.execute(f\"SELECT * FROM users WHERE name = {name}\")\\n')]<|tool_call_end|>"
            if "ZERO-TRUST QA MANDATE" in pu:
                return "VERDICT: PASSED"
            if "ZERO-TRUST SECURITY MANDATE" in pu:
                return "VERDICT: FAILED (Reason: Critical SQL Injection vulnerability in get_user)"
            if "AUTONOMOUS SWARM AUTO-JUDGE" in pu:
                return "DECISION: REJECTED (Diagnostics: Fix SQL Injection vulnerability)"
            return "OK"

        async def run():
            with patch("swarm.loop_engine.query_local_slot", side_effect=mock_query_local_slot), \
                 patch("swarm.loop_engine.query_qwen_web", new_callable=AsyncMock, return_value="ok"), \
                 patch("swarm.loop_engine.ping_lead_advisor", new_callable=AsyncMock, return_value="g"), \
                 patch("swarm.loop_engine.run_test_suite", return_value={"success": True, "skipped": False, "runner": "pytest", "exit_code": 0}), \
                 patch("swarm.loop_engine.commit_changes") as mock_commit:
                out = await execute_zero_trust_task(
                    task, repo_block="", repo_path="", research_brief="", github_issue_num=None
                )
                return out, mock_commit

        result, mock_commit = asyncio.run(run())
        self.assertEqual(result["status"], "failed")
        self.assertFalse(result.get("security_passed"))
        self.assertIn("security verdict not PASSED", result.get("failure_reasons", []))
        mock_commit.assert_not_called()

    # ─────────────────────────────────────────────────────────────
    # 7. STAGE 4: ADVERSARIAL ORACLE / INVARIANT FAILURE
    # ─────────────────────────────────────────────────────────────
    def test_stage_4_oracle_or_invariant_rejection(self):
        """Stage 4: Adversarial Oracle flags broken invariants -> Auto-Judge rejects -> task fails."""
        task = {
            "id": "task-oracle-fail", "order": 1, "title": "State Transition",
            "role": "dev", "description": "Transition machine", "acceptance_criteria": "pass",
            "status": "pending", "attempts": 0, "advisor_consultations": [],
        }

        async def mock_query_local_slot(prompt, system="", **kwargs):
            pu = prompt.upper()
            if "SURGICAL CODE DRAFTSMAN" in pu:
                return "<|tool_call_start|>[write(path='src/state.py', content='state = \"INVALID\"\\n')]<|tool_call_end|>"
            if "ZERO-TRUST QA MANDATE" in pu:
                return "VERDICT: PASSED"
            if "ZERO-TRUST SECURITY MANDATE" in pu:
                return "VERDICT: PASSED"
            if "AUTONOMOUS SWARM AUTO-JUDGE" in pu:
                return "DECISION: REJECTED (Diagnostics: Oracle detected invalid state transition sequence)"
            return "OK"

        async def run():
            with patch("swarm.loop_engine.query_local_slot", side_effect=mock_query_local_slot), \
                 patch("swarm.loop_engine.query_qwen_web", new_callable=AsyncMock, return_value="CRITICAL: Violates SCXML transition state"), \
                 patch("swarm.loop_engine.ping_lead_advisor", new_callable=AsyncMock, return_value="g"), \
                 patch("swarm.loop_engine.run_test_suite", return_value={"success": True, "skipped": False, "runner": "pytest", "exit_code": 0}), \
                 patch("swarm.loop_engine.commit_changes") as mock_commit:
                out = await execute_zero_trust_task(
                    task, repo_block="", repo_path="", research_brief="", github_issue_num=None
                )
                return out, mock_commit

        result, mock_commit = asyncio.run(run())
        self.assertEqual(result["status"], "failed")
        self.assertIn("auto-judge did not issue DECISION: APPROVED", result.get("failure_reasons", []))
        mock_commit.assert_not_called()

    # ─────────────────────────────────────────────────────────────
    # 8. STAGE 5: AUTO-JUDGE GATE DECISION REJECTION
    # ─────────────────────────────────────────────────────────────
    def test_stage_5_auto_judge_rejection_after_retries(self):
        """Stage 5: Auto-Judge explicitly outputs DECISION: REJECTED on every attempt -> task fails cleanly."""
        task = {
            "id": "task-judge-reject", "order": 1, "title": "Rejected Feature",
            "role": "dev", "description": "Implementation", "acceptance_criteria": "Clean Arch",
            "status": "pending", "attempts": 0, "advisor_consultations": [],
        }

        async def mock_query_local_slot(prompt, system="", **kwargs):
            pu = prompt.upper()
            if "SURGICAL CODE DRAFTSMAN" in pu:
                return "<|tool_call_start|>[write(path='src/feature.py', content='x = 42\\n')]<|tool_call_end|>"
            if "ZERO-TRUST QA MANDATE" in pu:
                return "VERDICT: PASSED"
            if "ZERO-TRUST SECURITY MANDATE" in pu:
                return "VERDICT: PASSED"
            if "AUTONOMOUS SWARM AUTO-JUDGE" in pu:
                return "DECISION: REJECTED (Diagnostics: Violates Clean Architecture boundaries)"
            return "OK"

        async def run():
            with patch("swarm.loop_engine.query_local_slot", side_effect=mock_query_local_slot), \
                 patch("swarm.loop_engine.query_qwen_web", new_callable=AsyncMock, return_value="ok"), \
                 patch("swarm.loop_engine.ping_lead_advisor", new_callable=AsyncMock, return_value="g"), \
                 patch("swarm.loop_engine.run_test_suite", return_value={"success": True, "skipped": False, "runner": "pytest", "exit_code": 0}), \
                 patch("swarm.loop_engine.commit_changes") as mock_commit:
                out = await execute_zero_trust_task(
                    task, repo_block="", repo_path="", research_brief="", github_issue_num=None
                )
                return out, mock_commit

        result, mock_commit = asyncio.run(run())
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["attempts"], 3)
        self.assertIn("auto-judge did not issue DECISION: APPROVED", result.get("failure_reasons", []))
        mock_commit.assert_not_called()

    # ─────────────────────────────────────────────────────────────
    # 9. STAGE 6: FINAL MERGE HONESTY GATE (EMPTY DELIVERABLE)
    # ─────────────────────────────────────────────────────────────
    def test_stage_6_final_merge_blocked_when_zero_code_produced(self):
        """Stage 6: When tasks complete with 0 files written, merge is honestly blocked."""
        with tempfile.TemporaryDirectory() as td:
            repo_p = Path(td)
            subprocess.run(["git", "init", "-b", "main", str(repo_p)], capture_output=True, check=True)
            (repo_p / "README.md").write_text("# Project\n")
            subprocess.run(["git", "-C", str(repo_p), "add", "-A"], check=True)
            subprocess.run(["git", "-C", str(repo_p), "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-m", "init"], check=True)

            sess = create_new_loop_session(title="Empty Feature", goal="Do Nothing", repo_path=str(repo_p))
            sess_id = sess["id"]

            async def run():
                with patch("swarm.loop_engine.query_gemini", new_callable=AsyncMock, return_value="Summary"), \
                     patch("swarm.loop_engine.merge_branch") as mock_merge:
                    le.LOOP_STATE["id"] = sess_id
                    le.LOOP_STATE["session_id"] = sess_id
                    le.LOOP_STATE["goal"] = "Do Nothing"
                    le.LOOP_STATE["repo_path"] = str(repo_p)
                    le.LOOP_STATE["status"] = "running"
                    le.LOOP_STATE["target_branch"] = "main"
                    le.LOOP_STATE["git_branch"] = "swarm/loop-test"
                    le.LOOP_STATE["tasks"] = [
                        {
                            "id": "t1", "title": "Doc Task", "role": "dev",
                            "status": "completed", "files_written": [], "qa_passed": True
                        }
                    ]
                    await _async_loop_runner()
                    return mock_merge

            mock_merge = asyncio.run(run())
            state = get_loop_state()
            self.assertEqual(state["status"], "completed")
            self.assertFalse(state.get("produced_code"))
            self.assertEqual(state.get("files_written_total"), 0)
            mock_merge.assert_not_called()
            delete_loop_session(sess_id)

    # ─────────────────────────────────────────────────────────────
    # 10. STAGE 7: DAG DEADLOCK / STALLED DEPENDENCY FAILURE
    # ─────────────────────────────────────────────────────────────
    def test_stage_7_dag_deadlock_fails_cleanly(self):
        """Stage 7: Tasks have circular or missing dependency -> pipeline stalls -> loop transitions to failed."""
        with tempfile.TemporaryDirectory() as td:
            repo_p = Path(td)
            subprocess.run(["git", "init", "-b", "main", str(repo_p)], capture_output=True, check=True)
            (repo_p / "README.md").write_text("# Project\n")
            subprocess.run(["git", "-C", str(repo_p), "add", "-A"], check=True)
            subprocess.run(["git", "-C", str(repo_p), "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-m", "init"], check=True)

            sess = create_new_loop_session(title="Deadlock Feature", goal="Deadlock Test", repo_path=str(repo_p))
            sess_id = sess["id"]

            async def run():
                le.LOOP_STATE["id"] = sess_id
                le.LOOP_STATE["session_id"] = sess_id
                le.LOOP_STATE["goal"] = "Deadlock Test"
                le.LOOP_STATE["repo_path"] = str(repo_p)
                le.LOOP_STATE["status"] = "running"
                le.LOOP_STATE["tasks"] = [
                    {"id": "t1", "title": "Task 1", "role": "dev", "status": "pending", "dependencies": ["non-existent-task"]}
                ]
                await _async_loop_runner()

            asyncio.run(run())
            state = get_loop_state()
            self.assertEqual(state["status"], "failed")
            self.assertIn("Task pipeline stalled", state.get("final_summary", ""))
            delete_loop_session(sess_id)


if __name__ == "__main__":
    unittest.main()
