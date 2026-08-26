"""
Unit Tests for Autonomous Loop Crash Resilience & Auto-Resume on Server Startup
Tests atomic checkpoints, interrupted run auto-detection, and resume execution without restart from step 0.
"""

import unittest
import asyncio
import json
import time
import uuid
import tempfile
import threading
from pathlib import Path
from unittest.mock import patch, AsyncMock, MagicMock
from http.server import HTTPServer
import urllib.request

from swarm.config import LOOP_SESSIONS_DIR, SESSIONS_DIR
from swarm.sessions import (
    atomic_write_json,
    detect_and_recover_interrupted_sessions,
    create_new_loop_session,
    load_loop_session,
    save_loop_session,
    delete_loop_session,
    list_loop_sessions
)
from swarm.loop_engine import (
    get_loop_state,
    select_loop_session,
    start_loop,
    stop_loop,
    pause_loop,
    resume_loop,
    auto_resume_on_startup,
    execute_zero_trust_task,
    _async_loop_runner,
    SWARM_LOOP_ROSTER
)
from swarm.server import SwarmHandler

class TestLoopResilience(unittest.TestCase):
    def tearDown(self):
        stop_loop()

    def test_atomic_write_json_resilience(self):
        """Test atomic_write_json writes safely and handles write errors without corrupting target."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir) / "test_session.json"
            initial_data = {"id": "loop_123", "status": "running", "step": 1}
            
            # 1. Normal write
            atomic_write_json(target, initial_data)
            self.assertTrue(target.exists())
            self.assertEqual(json.loads(target.read_text()), initial_data)

            # 2. Simulate error mid-write to temporary file
            with patch.object(Path, "write_text", side_effect=IOError("Disk write failure")):
                with self.assertRaises(IOError):
                    atomic_write_json(target, {"id": "loop_123", "status": "corrupted", "step": 2})

            # Verify original target file is completely unharmed and intact
            reloaded = json.loads(target.read_text())
            self.assertEqual(reloaded["status"], "running")
            self.assertEqual(reloaded["step"], 1)

    def test_detect_and_recover_interrupted_runs_on_startup(self):
        """Test server startup detects 'running' sessions, marks them 'interrupted', and cleans orphan temp files."""
        sess = create_new_loop_session(
            title="Interrupted Test Run",
            goal="Build Real-Time Notification System"
        )
        sess_id = sess["id"]
        
        # Simulate server crash while session was running
        raw = load_loop_session(sess_id)
        raw["status"] = "running"
        raw["research_brief"] = "# Research Brief\n\nNotification Engine Architecture"
        raw["tasks"] = [
            {"id": "task-1", "title": "Create WebSocket Hub", "status": "completed", "role": "dev"},
            {"id": "task-2", "title": "Implement Redis PubSub", "status": "in_progress", "role": "dev", "attempts": 2}
        ]
        save_loop_session(raw)

        # Create an orphan temp file in loop_sessions to simulate crash during write
        orphan_tmp = LOOP_SESSIONS_DIR / f"{sess_id}.tmp.9999.abcd12"
        orphan_tmp.write_text("corrupted partial json", encoding="utf-8")
        self.assertTrue(orphan_tmp.exists())

        # Run recovery
        interrupted = detect_and_recover_interrupted_sessions()
        recovered_ids = [s.get("session_id") or s.get("id") for s in interrupted]
        self.assertIn(sess_id, recovered_ids)

        # Check that orphan temp file was cleaned up
        self.assertFalse(orphan_tmp.exists())

        # Check session is marked 'interrupted' with timestamp and log
        reloaded = load_loop_session(sess_id)
        self.assertEqual(reloaded["status"], "interrupted")
        self.assertGreater(reloaded.get("interrupted_at", 0), 0)
        self.assertTrue(any("Server was restarted or terminated" in log.get("message", "") for log in reloaded.get("live_logs", [])))

        # Clean up
        delete_loop_session(sess_id)

    def test_auto_resume_on_startup(self):
        """Test auto_resume_on_startup triggers resume_loop for latest interrupted session when enabled."""
        sess = create_new_loop_session(
            title="Auto Resume Test",
            goal="Optimize Database Indexes"
        )
        sess_id = sess["id"]
        raw = load_loop_session(sess_id)
        raw["status"] = "running"
        raw["goal"] = "Optimize Database Indexes"
        save_loop_session(raw)

        # Ensure AUTO_RESUME_ON_START is True
        with patch("swarm.loop_engine.AUTO_RESUME_ON_START", True), \
             patch("swarm.loop_engine._thread_worker"):
            res = auto_resume_on_startup()
            self.assertIsNotNone(res)
            self.assertTrue(res.get("success"))
            self.assertEqual(res.get("status"), "running")
            self.assertEqual(res.get("session_id"), sess_id)

        delete_loop_session(sess_id)

    def test_resume_skips_research_and_completed_tasks(self):
        """Test resuming does not start from step 0: skips research, skips completed tasks, resumes in-progress task."""
        sess = create_new_loop_session(
            title="Resume Skip Test",
            goal="Add JWT Auth Middleware",
            repo_path="/mock/repo"
        )
        sess_id = sess["id"]

        # Populate pre-existing research brief and tasks
        existing_brief = "# Pre-Flight Research Brief\n\nJWT Token verification signatures and claims."
        tasks = [
            {
                "id": "task-1",
                "order": 1,
                "title": "Token Generator",
                "role": "dev",
                "status": "completed",
                "attempts": 1,
                "output": "def generate_token(): pass",
                "qa_verdict": "PASSED",
                "security_verdict": "PASSED",
                "oracle_verdict": "Consensus OK",
                "judge_certificate": "APPROVED"
            },
            {
                "id": "task-2",
                "order": 2,
                "title": "Auth Middleware Guard",
                "role": "dev",
                "status": "in_progress",
                "attempts": 1,
                "output": "",
                "description": "Validate Bearer token header in request",
                "acceptance_criteria": "401 on missing token, 200 on valid token"
            }
        ]
        github_issue = {"issue_number": 42, "url": "https://github.com/org/repo/issues/42"}

        session_data = load_loop_session(sess_id)
        session_data["status"] = "interrupted"
        session_data["research_brief"] = existing_brief
        session_data["tasks"] = tasks
        session_data["github_issue"] = github_issue
        save_loop_session(session_data)

        # Select the session
        select_loop_session(sess_id)

        research_called = False
        decompose_called = False
        task1_called = False
        task2_called = False
        github_comments = []

        async def mock_research(*args, **kwargs):
            nonlocal research_called
            research_called = True
            return {"content": "New Brief", "filename": "new.md"}

        async def mock_decompose(*args, **kwargs):
            nonlocal decompose_called
            decompose_called = True
            return []

        async def mock_execute_task(task, *args, **kwargs):
            nonlocal task1_called, task2_called
            if task["id"] == "task-1":
                task1_called = True
            elif task["id"] == "task-2":
                task2_called = True
                task["status"] = "completed"
                task["attempts"] = 2
                task["output"] = "def auth_middleware(): return True"
                task["judge_certificate"] = "APPROVED"
            return task

        def mock_gh_comment(repo_path, issue_num, body):
            github_comments.append({"issue": issue_num, "body": body})
            return {"success": True}

        with patch("swarm.loop_engine.run_preflight_research", side_effect=mock_research), \
             patch("swarm.loop_engine.decompose_goal_into_tasks", side_effect=mock_decompose), \
             patch("swarm.loop_engine.execute_zero_trust_task", side_effect=mock_execute_task), \
             patch("swarm.loop_engine.gh_issue_comment", side_effect=mock_gh_comment), \
             patch("swarm.loop_engine.gh_issue_close", return_value={"success": True}), \
             patch("swarm.loop_engine.query_gemini", new_callable=AsyncMock, return_value="Final Executive Summary & Verification Sign-Off"):

            # Run async loop runner directly
            asyncio.run(_async_loop_runner())

            # Verifications:
            # 1. Research subagent was SKIPPED because research_brief already existed
            self.assertFalse(research_called, "Pre-Flight Research subagent should have been skipped on resume!")

            # 2. Decompose was SKIPPED because tasks already existed
            self.assertFalse(decompose_called, "Task decomposition should have been skipped on resume!")

            # 3. Task 1 was SKIPPED because status was 'completed'
            self.assertFalse(task1_called, "Task 1 was completed and should have been skipped!")

            # 4. Task 2 was executed
            self.assertTrue(task2_called, "Task 2 was in_progress and should have been executed!")

            # 5. GitHub reconnected comment was posted
            self.assertTrue(any("Server restarted. Resuming task execution" in c["body"] for c in github_comments),
                            "GitHub restart comment should have been posted!")

            # 6. Session final state is completed
            state = get_loop_state()
            self.assertEqual(state["status"], "completed")
            self.assertIn("Final Executive Summary", state["final_summary"])

        delete_loop_session(sess_id)

    def test_granular_checkpoints_saved_at_each_stage(self):
        """Test that execute_zero_trust_task saves checkpoints after dev, qa, sec, oracle, and judge stages."""
        sess = create_new_loop_session(title="Checkpoint Test", goal="Checkpoint Invariants")
        select_loop_session(sess["id"])

        task = {
            "id": "task-cp-1",
            "order": 1,
            "title": "Verify Granular Checkpoint Saves",
            "role": "dev",
            "description": "Implement checkpoint tests",
            "acceptance_criteria": "Zero defects",
            "status": "pending",
            "assigned_agent": "⚙️ Surgical Code Draftsman",
            "assigned_slot": "Liquid LFM 2.5 (Slot 2)",
            "attempts": 0,
            "advisor_consultations": []
        }

        stage_records = []
        original_save = save_loop_session

        def checkpoint_tracker(state):
            tasks = state.get("tasks", [])
            for t in tasks:
                if t.get("id") == "task-cp-1" and t.get("stage"):
                    stage_records.append((t.get("stage"), t.get("attempts")))
            original_save(state)

        async def run_task():
            async def mock_slot(prompt, system=""):
                pu = prompt.upper()
                if "SURGICAL CODE DRAFTSMAN" in pu:
                    return "def checkpoint_code(): return True"
                elif "ZERO-TRUST QA MANDATE" in pu:
                    return "VERDICT: PASSED"
                elif "ZERO-TRUST SECURITY MANDATE" in pu:
                    return "VERDICT: PASSED"
                elif "AUTONOMOUS SWARM AUTO-JUDGE" in pu:
                    return "DECISION: APPROVED (Certificate: Verified)"
                return "OK"

            with patch("swarm.loop_engine.save_loop_session", side_effect=checkpoint_tracker), \
                 patch("swarm.loop_engine.query_local_slot", side_effect=mock_slot), \
                 patch("swarm.loop_engine.query_qwen_web", new_callable=AsyncMock, return_value="Consensus OK"), \
                 patch("swarm.loop_engine.ping_lead_advisor", new_callable=AsyncMock, return_value="Advise"):

                # Attach task to LOOP_STATE
                LOOP_STATE_OBJ = get_loop_state()
                LOOP_STATE_OBJ["tasks"] = [task]

                await execute_zero_trust_task(
                    task,
                    repo_block="",
                    repo_path="",
                    research_brief="Brief",
                    github_issue_num=None
                )

        asyncio.run(run_task())

        # Verify all granular checkpoint stages were recorded:
        recorded_stages = [r[0] for r in stage_records]
        self.assertIn("dev_draft_completed", recorded_stages)
        self.assertIn("qa_completed", recorded_stages)
        self.assertIn("security_completed", recorded_stages)
        self.assertIn("oracle_completed", recorded_stages)
        self.assertIn("judge_completed", recorded_stages)
        self.assertEqual(task["status"], "completed")

        delete_loop_session(sess["id"])


class TestServerLoopResumeEndpoint(unittest.TestCase):
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

    def _req(self, path, method="GET", data=None):
        url = f"http://127.0.0.1:{self.port}{path}"
        headers = {"Content-Type": "application/json"} if data is not None else {}
        body = json.dumps(data).encode("utf-8") if data is not None else None
        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))

    def test_api_loop_resume_endpoint_with_session_id(self):
        """Test POST /api/loop/resume with explicit session_id resumes that session."""
        sess = create_new_loop_session(title="API Resume Test", goal="Build OAuth2 Flow")
        sess_id = sess["id"]
        sess_data = load_loop_session(sess_id)
        sess_data["status"] = "interrupted"
        save_loop_session(sess_data)

        with patch("swarm.loop_engine._thread_worker"):
            status, res = self._req("/api/loop/resume", method="POST", data={"session_id": sess_id})
            self.assertEqual(status, 200)
            self.assertTrue(res.get("success"))
            self.assertEqual(res.get("status"), "running")
            self.assertEqual(res.get("session_id"), sess_id)

        delete_loop_session(sess_id)

if __name__ == "__main__":
    unittest.main()
