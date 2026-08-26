"""
Unit Tests for Autonomous Loop Agent Engine & Advisor Ping
"""

import unittest
import asyncio
from pathlib import Path
from unittest.mock import patch, AsyncMock
from swarm.loop_engine import (
    get_loop_state,
    start_loop,
    pause_loop,
    resume_loop,
    stop_loop,
    decompose_goal_into_tasks,
    ping_lead_advisor
)

class TestLoopEngine(unittest.TestCase):
    def tearDown(self):
        stop_loop()

    def test_loop_state_structure(self):
        state = get_loop_state()
        self.assertIn("status", state)
        self.assertIn("tasks", state)
        self.assertIn("advisor_pings", state)

    def test_loop_lifecycle_controls(self):
        with patch("swarm.loop_engine._thread_worker"):
            # Test start
            res = start_loop("Test Feature Loop", repo_path="")
            self.assertTrue(res["success"])
            self.assertEqual(get_loop_state()["status"], "running")

            # Test pause
            pause_res = pause_loop()
            self.assertTrue(pause_res["success"])
            self.assertEqual(get_loop_state()["status"], "paused")

            # Test resume
            resume_res = resume_loop()
            self.assertTrue(resume_res["success"])
            self.assertEqual(get_loop_state()["status"], "running")

            # Test stop
            stop_res = stop_loop()
            self.assertTrue(stop_res["success"])
            self.assertEqual(get_loop_state()["status"], "idle")

    def test_decompose_tasks_fallback(self):
        async def run_test():
            with patch("swarm.loop_engine.query_gemini", new_callable=AsyncMock) as mock_gemini:
                mock_gemini.return_value = """[
                    {"title": "Code Draft", "role": "dev", "description": "Dev", "acceptance_criteria": "Done"},
                    {"title": "QA Tests", "role": "qa", "description": "QA", "acceptance_criteria": "Done"},
                    {"title": "Security Audit", "role": "review", "description": "Security", "acceptance_criteria": "Done"}
                ]"""
                tasks = await decompose_goal_into_tasks("Implement Redis Lock", "", "Research brief context")
                self.assertEqual(len(tasks), 3)
                self.assertEqual(tasks[0]["role"], "dev")
                self.assertEqual(tasks[1]["role"], "qa")
                self.assertEqual(tasks[2]["role"], "review")

        asyncio.run(run_test())

    def test_advisor_ping(self):
        async def run_test():
            with patch("swarm.loop_engine.query_gemini", new_callable=AsyncMock) as mock_gemini:
                mock_gemini.return_value = "Use RS256 for asymmetric signature verification."
                ans = await ping_lead_advisor("Surgical Draftsman", "dev", "RS256 vs HS256?", "Auth task")
                self.assertIn("RS256", ans)
                state = get_loop_state()
                self.assertGreater(len(state["advisor_pings"]), 0)

        asyncio.run(run_test())

    def test_preflight_research_subagent(self):
        async def run_test():
            from swarm.loop_engine import run_preflight_research
            with patch("swarm.loop_engine.query_gemini", new_callable=AsyncMock) as mock_gemini, \
                 patch("swarm.loop_engine.fetch_latest_doc_context", return_value="Redis 7.2 Async Cluster API"):
                mock_gemini.return_value = "# Pre-Flight Research Brief\n\n## 1. Executive Architecture\nVerified APIs and symbols."
                res = await run_preflight_research("Implement Redis Caching", "", "Repo Block")
                self.assertIn("content", res)
                self.assertIn("filename", res)
                self.assertIn("Research Brief", res["content"])
                self.assertTrue(len(get_loop_state()["research_brief"]) > 0)

        asyncio.run(run_test())

    def test_zero_trust_handoff_with_retry_and_auto_judge(self):
        async def run_test():
            from swarm.loop_engine import execute_zero_trust_task
            
            task = {
                "id": "task-1",
                "order": 1,
                "title": "Build Distributed Lock",
                "role": "dev",
                "description": "Construct Redis lock with ttl",
                "acceptance_criteria": "Tests pass, zero injection risks",
                "status": "pending",
                "assigned_agent": "⚙️ Surgical Code Draftsman",
                "assigned_slot": "Liquid LFM 2.5 (Slot 2)",
                "advisor_consultations": []
            }

            slot_call_count = 0
            async def mock_local_slot(prompt, system="", **kwargs):
                nonlocal slot_call_count
                slot_call_count += 1
                prompt_u = prompt.upper()
                if "SURGICAL CODE DRAFTSMAN" in prompt_u:
                    return (
                        "<|tool_call_start|>[write(path='src/lock.py', "
                        "content='def acquire_lock(key, ttl):\\n    return True\\n'), "
                        "write(path='tests/test_lock.py', "
                        "content=\"def test_lock():\\n    assert True\\n\")]<|tool_call_end|>"
                    )
                elif "ZERO-TRUST QA MANDATE" in prompt_u:
                    # Fail on first attempt, pass on second attempt
                    if slot_call_count <= 3:
                        return "QA AUDIT: Missing timeout assertion.\nVERDICT: FAILED (Reason: no timeout test)"
                    return "QA AUDIT: Syntax valid, tests pass.\nVERDICT: PASSED"
                elif "ZERO-TRUST SECURITY MANDATE" in prompt_u:
                    return "SECURITY AUDIT: No injection vectors detected.\nVERDICT: PASSED"
                elif "AUTONOMOUS SWARM AUTO-JUDGE" in prompt_u:
                    if slot_call_count <= 4:
                        return "DECISION: REJECTED (Diagnostics: Fix missing timeout test)"
                    return "DECISION: APPROVED (Certificate: Verified by Swarm Auto-Judge)"
                return "OK"

            with patch("swarm.loop_engine.query_local_slot", side_effect=mock_local_slot), \
                 patch("swarm.loop_engine.query_qwen_web", new_callable=AsyncMock) as mock_qwen, \
                 patch("swarm.loop_engine.ping_lead_advisor", new_callable=AsyncMock) as mock_ping:
                
                mock_qwen.return_value = "Consensus verified."
                mock_ping.return_value = "Ensure TTL expiration handling."

                completed_task = await execute_zero_trust_task(
                    task,
                    repo_block="",
                    repo_path="",
                    research_brief="Research Brief",
                    github_issue_num=None
                )

                self.assertEqual(completed_task["status"], "completed")
                self.assertEqual(completed_task["attempts"], 2)
                self.assertIn("acquire_lock", completed_task["output"])
                self.assertIn("APPROVED", completed_task["judge_certificate"])
                self.assertTrue(len(completed_task["injected_skill"]) > 0)

        asyncio.run(run_test())

    def test_real_file_writing_and_test_execution_in_task(self):
        """Test execute_zero_trust_task writes real files, executes real test commands, and creates git commits."""
        import tempfile
        import subprocess
        from swarm.git_engine import commit_changes
        from swarm.loop_engine import execute_zero_trust_task

        async def run_test():
            with tempfile.TemporaryDirectory() as tmpdir:
                # 1. Initialize git repo
                subprocess.run(["git", "-C", tmpdir, "init", "-b", "main"], check=True, capture_output=True)
                subprocess.run(["git", "-C", tmpdir, "config", "user.name", "Test User"], check=True)
                subprocess.run(["git", "-C", tmpdir, "config", "user.email", "test@user.com"], check=True)
                
                (Path(tmpdir) / "README.md").write_text("# Project")
                commit_changes(tmpdir, "Initial commit")

                task = {
                    "id": "task-real-1",
                    "order": 1,
                    "title": "Implement Token Generator",
                    "role": "dev",
                    "description": "Generate auth tokens",
                    "acceptance_criteria": "Tests pass 100%",
                    "status": "pending",
                    "assigned_agent": "⚙️ Surgical Code Draftsman",
                    "assigned_slot": "Slot 2",
                    "advisor_consultations": []
                }

                dev_code_output = """Here is the implementation:

```python filepath=src/token_service.py
def generate_token(user_id: str) -> str:
    return f"token-{user_id}"
```

### `tests/test_token_service.py`
```python
import unittest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from src.token_service import generate_token

class TestTokenService(unittest.TestCase):
    def test_generate(self):
        self.assertEqual(generate_token("alice"), "token-alice")

if __name__ == "__main__":
    unittest.main()
```
"""
                async def mock_slot(prompt, system="", **kwargs):
                    pu = prompt.upper()
                    if "SURGICAL CODE DRAFTSMAN" in pu:
                        return dev_code_output
                    elif "ZERO-TRUST QA MANDATE" in pu:
                        return "QA AUDIT: Verified assertions.\nVERDICT: PASSED"
                    elif "ZERO-TRUST SECURITY MANDATE" in pu:
                        return "SECURITY AUDIT: Safe token construction.\nVERDICT: PASSED"
                    elif "AUTONOMOUS SWARM AUTO-JUDGE" in pu:
                        return "DECISION: APPROVED (Certificate: Verified by Swarm Auto-Judge)"
                    return "OK"

                with patch("swarm.loop_engine.query_local_slot", side_effect=mock_slot), \
                     patch("swarm.loop_engine.query_qwen_web", new_callable=AsyncMock, return_value="Consensus OK"), \
                     patch("swarm.loop_engine.ping_lead_advisor", new_callable=AsyncMock, return_value="Guidance"):

                    completed_task = await execute_zero_trust_task(
                        task,
                        repo_block="",
                        repo_path=tmpdir,
                        research_brief="Research Brief",
                        github_issue_num=None
                    )

                    # 1. Verification of real file writes
                    self.assertTrue((Path(tmpdir) / "src" / "token_service.py").exists())
                    self.assertTrue((Path(tmpdir) / "tests" / "test_token_service.py").exists())
                    self.assertIn("src/token_service.py", completed_task["files_written"])
                    self.assertIn("tests/test_token_service.py", completed_task["files_written"])

                    # 2. Verification of real test execution results
                    self.assertIn("test_results", completed_task)
                    self.assertTrue(completed_task["test_results"]["success"])
                    self.assertEqual(completed_task["test_results"]["exit_code"], 0)

                    # 3. Verification of git commit
                    self.assertTrue(len(completed_task.get("commit_hash", "")) > 0)
                    self.assertEqual(completed_task["status"], "completed")

        asyncio.run(run_test())

    def test_real_loop_branch_isolation_and_merge_to_main(self):
        """Test full loop run creates isolated branch, applies code, tests, and merges to main."""
        import tempfile
        import subprocess
        from swarm.git_engine import commit_changes
        from swarm.loop_engine import _async_loop_runner, start_loop, stop_loop, select_loop_session, create_new_loop_session

        async def run_test():
            with tempfile.TemporaryDirectory() as tmpdir:
                # 1. Initialize git repo
                subprocess.run(["git", "-C", tmpdir, "init", "-b", "main"], check=True, capture_output=True)
                subprocess.run(["git", "-C", tmpdir, "config", "user.name", "Test User"], check=True)
                subprocess.run(["git", "-C", tmpdir, "config", "user.email", "test@user.com"], check=True)
                
                (Path(tmpdir) / "README.md").write_text("# Main App")
                commit_changes(tmpdir, "Initial commit")

                # Setup Loop Session
                sess = create_new_loop_session(
                    title="Build Health Check",
                    goal="Add health check module",
                    repo_path=tmpdir
                )
                select_loop_session(sess["id"])
                state = get_loop_state()
                state["repo_path"] = tmpdir
                state["goal"] = "Add health check module"
                state["research_brief"] = "# Brief\nHealth check"
                state["tasks"] = [
                    {
                        "id": "task-1",
                        "order": 1,
                        "title": "Add Health Endpoint",
                        "role": "dev",
                        "description": "Implement health check",
                        "acceptance_criteria": "Tests pass",
                        "status": "pending"
                    }
                ]

                dev_code = """```python filepath=health.py
def check_health():
    return {"status": "ok"}
```
### `tests/test_health.py`
```python
import unittest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from health import check_health

class TestHealth(unittest.TestCase):
    def test_health(self):
        self.assertEqual(check_health()["status"], "ok")

if __name__ == "__main__":
    unittest.main()
```
"""
                async def mock_slot(prompt, system="", **kwargs):
                    pu = prompt.upper()
                    if "SURGICAL CODE DRAFTSMAN" in pu:
                        return dev_code
                    elif "ZERO-TRUST QA MANDATE" in pu:
                        return "QA AUDIT: Verified.\nVERDICT: PASSED"
                    elif "ZERO-TRUST SECURITY MANDATE" in pu:
                        return "SECURITY AUDIT: Verified.\nVERDICT: PASSED"
                    elif "AUTONOMOUS SWARM AUTO-JUDGE" in pu:
                        return "DECISION: APPROVED"
                    return "Executive Summary"

                with patch("swarm.loop_engine.query_local_slot", side_effect=mock_slot), \
                     patch("swarm.loop_engine.query_gemini", new_callable=AsyncMock, return_value="Executive Summary & Final Sign-Off"), \
                     patch("swarm.loop_engine.query_qwen_web", new_callable=AsyncMock, return_value="Consensus verified"):

                    await _async_loop_runner()

                    final_state = get_loop_state()
                    self.assertEqual(final_state["status"], "completed")
                    self.assertTrue(len(final_state.get("merge_commit", "")) > 0)

                    # Verify code is present in main repo
                    self.assertTrue((Path(tmpdir) / "health.py").exists())
                    self.assertTrue((Path(tmpdir) / "tests" / "test_health.py").exists())

        asyncio.run(run_test())

    def test_auto_judge_retry_on_test_failure(self):
        """Test that real test failure triggers retry loop with failure trace and succeeds after fix."""
        import tempfile
        import subprocess
        from swarm.git_engine import commit_changes
        from swarm.loop_engine import execute_zero_trust_task

        async def run_test():
            with tempfile.TemporaryDirectory() as tmpdir:
                subprocess.run(["git", "-C", tmpdir, "init", "-b", "main"], check=True, capture_output=True)
                subprocess.run(["git", "-C", tmpdir, "config", "user.name", "Test User"], check=True)
                subprocess.run(["git", "-C", tmpdir, "config", "user.email", "test@user.com"], check=True)
                (Path(tmpdir) / "README.md").write_text("# Test Repo")
                commit_changes(tmpdir, "Init")

                task = {
                    "id": "task-retry-1",
                    "order": 1,
                    "title": "Math Multiplier",
                    "role": "dev",
                    "description": "Multiply two numbers",
                    "acceptance_criteria": "Tests pass",
                    "status": "pending",
                    "assigned_agent": "⚙️ Surgical Code Draftsman",
                    "assigned_slot": "Slot 2",
                    "advisor_consultations": []
                }

                dev_attempt_count = 0
                async def mock_slot(prompt, system="", **kwargs):
                    nonlocal dev_attempt_count
                    pu = prompt.upper()
                    if "SURGICAL CODE DRAFTSMAN" in pu:
                        dev_attempt_count += 1
                        if dev_attempt_count == 1:
                            # Failing code on attempt 1
                            return """```python filepath=math_mod.py
def multiply(a, b):
    return a + b # BUG: wrong operator!
```
### `tests/test_math_mod.py`
```python
import unittest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from math_mod import multiply

class TestMath(unittest.TestCase):
    def test_multiply(self):
        self.assertEqual(multiply(2, 3), 6)

if __name__ == "__main__":
    unittest.main()
```"""
                        else:
                            # Fixed code on attempt 2
                            return """```python filepath=math_mod.py
def multiply(a, b):
    return a * b # FIXED!
```
### `tests/test_math_mod.py`
```python
import unittest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from math_mod import multiply

class TestMath(unittest.TestCase):
    def test_multiply(self):
        self.assertEqual(multiply(2, 3), 6)

if __name__ == "__main__":
    unittest.main()
```"""
                    elif "ZERO-TRUST QA MANDATE" in pu:
                        if "REAL TEST EXECUTION FAILED" in prompt:
                            return "VERDICT: FAILED (Reason: Unit tests failed with AssertionError)"
                        return "QA AUDIT: Verified.\nVERDICT: PASSED"
                    elif "ZERO-TRUST SECURITY MANDATE" in pu:
                        return "VERDICT: PASSED"
                    elif "AUTONOMOUS SWARM AUTO-JUDGE" in pu:
                        if "REAL TEST EXECUTION" in prompt and "Success: False" in prompt:
                            return "DECISION: REJECTED (Diagnostics: Fix math_mod operator bug)"
                        return "DECISION: APPROVED (Certificate: Math tests passed 100%)"
                    return "OK"

                with patch("swarm.loop_engine.query_local_slot", side_effect=mock_slot), \
                     patch("swarm.loop_engine.query_qwen_web", new_callable=AsyncMock, return_value="Consensus verified"), \
                     patch("swarm.loop_engine.ping_lead_advisor", new_callable=AsyncMock, return_value="Check multiplication"):

                    completed_task = await execute_zero_trust_task(
                        task,
                        repo_block="",
                        repo_path=tmpdir,
                        research_brief="Research Brief",
                        github_issue_num=None
                    )

                    # Should have retried and completed on attempt 2
                    self.assertEqual(completed_task["attempts"], 2)
                    self.assertEqual(completed_task["status"], "completed")
                    self.assertTrue(completed_task["test_results"]["success"])
                    self.assertEqual(completed_task["test_results"]["exit_code"], 0)
                    self.assertIn("multiply", (Path(tmpdir) / "math_mod.py").read_text())

        asyncio.run(run_test())

    def test_parallel_audit_phase_fanout(self):
        """Verify that parallel audit phase executes QA, Sec, and Oracle concurrently and updates SWARM_STATE."""
        async def run_test():
            from swarm.loop_engine import execute_zero_trust_task, SWARM_LOOP_ROSTER
            from swarm.orchestrator import SWARM_STATE, set_dynamic_subagents_roster

            set_dynamic_subagents_roster(SWARM_LOOP_ROSTER)

            task = {
                "id": "task-fanout-1",
                "order": 1,
                "title": "Parallel Auth Endpoint",
                "role": "dev",
                "description": "Auth with JWT",
                "acceptance_criteria": "Tests pass",
                "status": "pending",
                "assigned_agent": "⚙️ Surgical Code Draftsman",
                "assigned_slot": "Slot 2",
                "advisor_consultations": []
            }

            active_during_audit = []
            audit_start_times = {}

            async def mock_local_slot(prompt, system="", **kwargs):
                pu = prompt.upper()
                if "SURGICAL CODE DRAFTSMAN" in pu:
                    return (
                        "<|tool_call_start|>[write(path='src/auth.py', "
                        "content='def auth():\\n    return True\\n')]<|tool_call_end|>"
                    )
                elif "ZERO-TRUST QA MANDATE" in pu:
                    audit_start_times["qa"] = asyncio.get_event_loop().time()
                    active_during_audit.append({
                        "caller": "qa",
                        "qa_status": [s["status"] for s in SWARM_STATE["sub_agents"] if s["id"] == "agent_qa"][0],
                        "sec_status": [s["status"] for s in SWARM_STATE["sub_agents"] if s["id"] == "agent_sec"][0],
                        "oracle_status": [s["status"] for s in SWARM_STATE["sub_agents"] if s["id"] == "agent_oracle"][0]
                    })
                    await asyncio.sleep(0.05)
                    return "VERDICT: PASSED"
                elif "ZERO-TRUST SECURITY MANDATE" in pu:
                    audit_start_times["sec"] = asyncio.get_event_loop().time()
                    active_during_audit.append({
                        "caller": "sec",
                        "qa_status": [s["status"] for s in SWARM_STATE["sub_agents"] if s["id"] == "agent_qa"][0],
                        "sec_status": [s["status"] for s in SWARM_STATE["sub_agents"] if s["id"] == "agent_sec"][0],
                        "oracle_status": [s["status"] for s in SWARM_STATE["sub_agents"] if s["id"] == "agent_oracle"][0]
                    })
                    await asyncio.sleep(0.05)
                    return "VERDICT: PASSED"
                elif "AUTONOMOUS SWARM AUTO-JUDGE" in pu:
                    return "DECISION: APPROVED (Certificate: Fanout audit verified)"
                return "OK"

            async def mock_qwen(prompt):
                audit_start_times["oracle"] = asyncio.get_event_loop().time()
                await asyncio.sleep(0.05)
                return "Consensus verified."

            with patch("swarm.loop_engine.query_local_slot", side_effect=mock_local_slot), \
                 patch("swarm.loop_engine.query_qwen_web", side_effect=mock_qwen), \
                 patch("swarm.loop_engine.ping_lead_advisor", new_callable=AsyncMock, return_value="Guidance"):

                res = await execute_zero_trust_task(
                    task,
                    repo_block="",
                    repo_path="",
                    research_brief="Research Brief",
                    github_issue_num=None
                )

                self.assertEqual(res["status"], "completed")
                self.assertTrue(res["qa_passed"])
                self.assertTrue(res["security_passed"])
                self.assertIn("qa", audit_start_times)
                self.assertIn("sec", audit_start_times)
                self.assertIn("oracle", audit_start_times)
                # Verify that during audit execution, agents ran concurrently
                self.assertTrue(len(active_during_audit) >= 2)
                self.assertTrue(any(rec["qa_status"] == "running" and rec["sec_status"] == "running" for rec in active_during_audit))

        asyncio.run(run_test())

    def test_topological_dag_parallel_task_execution(self):
        """Verify parallel execution of independent tasks in topological DAG."""
        async def run_test():
            from swarm.loop_engine import _async_loop_runner, create_new_loop_session, select_loop_session, get_loop_state

            sess = create_new_loop_session(title="DAG Test", goal="Parallel DAG Execution")
            select_loop_session(sess["id"])
            state = get_loop_state()
            state["goal"] = "Parallel DAG Execution"
            state["research_brief"] = "# Pre-Flight Research Brief\nParallel DAG execution test brief context long enough."
            state["tasks"] = [
                {
                    "id": "task-dag-1",
                    "order": 1,
                    "title": "Build Module A",
                    "role": "dev",
                    "description": "Module A",
                    "acceptance_criteria": "Tests pass",
                    "dependencies": [],
                    "status": "pending"
                },
                {
                    "id": "task-dag-2",
                    "order": 2,
                    "title": "Build Module B",
                    "role": "dev",
                    "description": "Module B",
                    "acceptance_criteria": "Tests pass",
                    "dependencies": [],
                    "status": "pending"
                },
                {
                    "id": "task-dag-3",
                    "order": 3,
                    "title": "Synthesize A and B",
                    "role": "dev",
                    "description": "Integration",
                    "acceptance_criteria": "Tests pass",
                    "dependencies": ["task-dag-1", "task-dag-2"],
                    "status": "pending"
                }
            ]

            executed_order = []
            running_tasks = set()
            max_simultaneous_tasks = 0

            async def mock_execute_task(task, *args, **kwargs):
                nonlocal max_simultaneous_tasks
                running_tasks.add(task["id"])
                if len(running_tasks) > max_simultaneous_tasks:
                    max_simultaneous_tasks = len(running_tasks)
                await asyncio.sleep(0.05)
                task["status"] = "completed"
                task["output"] = f"Output for {task['id']}"
                executed_order.append(task["id"])
                running_tasks.remove(task["id"])
                return task

            with patch("swarm.loop_engine.execute_zero_trust_task", side_effect=mock_execute_task), \
                 patch("swarm.loop_engine.query_gemini", new_callable=AsyncMock, return_value="Final Summary"):

                await _async_loop_runner()

                final_state = get_loop_state()
                self.assertEqual(final_state["status"], "completed")
                # Tasks 1 & 2 ran in parallel before task 3
                self.assertIn("task-dag-1", executed_order[:2])
                self.assertIn("task-dag-2", executed_order[:2])
                self.assertEqual(executed_order[2], "task-dag-3")
                self.assertGreaterEqual(max_simultaneous_tasks, 2)

        asyncio.run(run_test())

    def test_thread_safe_state_logging_and_checkpoints(self):
        """Verify thread-safe concurrent state logging and checkpoints."""
        import threading
        from swarm.loop_engine import log_loop_activity, persist_active_loop_state, get_loop_state
        from swarm.orchestrator import update_agent_status, SWARM_STATE

        errors = []

        def worker(idx):
            try:
                for i in range(25):
                    log_loop_activity(f"Thread {idx} event {i}", category="test")
                    update_agent_status("sub_agents", f"agent_worker_{idx}", "running", f"Working {i}")
                    persist_active_loop_state()
                    st = get_loop_state()
                    self.assertIsNotNone(st.get("status"))
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(t,)) for t in range(6)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(errors), 0)
        final_logs = get_loop_state().get("live_logs", [])
        self.assertGreater(len(final_logs), 0)

if __name__ == "__main__":
    unittest.main()




