"""
Unit Tests for Auto-Dev Loop Sessions Persistence & Advisor-to-Loop Transfer
"""

import unittest
import asyncio
import time
from unittest.mock import patch, AsyncMock
from swarm.sessions import (
    create_new_session,
    load_session,
    save_session_turn,
    delete_session,
    create_new_loop_session,
    list_loop_sessions,
    load_loop_session,
    save_loop_session,
    delete_loop_session,
    rename_loop_session,
    link_advisor_and_loop_sessions
)
from swarm.loop_engine import (
    get_loop_state,
    select_loop_session,
    start_loop,
    stop_loop,
    pause_loop,
    resume_loop,
    async_transfer_advisor_to_loop,
    transfer_advisor_to_loop
)

class TestLoopSessions(unittest.TestCase):
    def tearDown(self):
        stop_loop()

    def test_loop_session_lifecycle(self):
        # 1. Create Loop Session
        sess = create_new_loop_session(
            title="Implement Distributed Locking",
            goal="Add Redis Distributed Lock with TTL",
            repo_path="/test/repo"
        )
        sess_id = sess["id"]
        self.assertTrue(sess_id.startswith("loop_"))
        self.assertEqual(sess["status"], "idle")
        self.assertEqual(sess["goal"], "Add Redis Distributed Lock with TTL")

        # 2. Save modifications to Loop Session
        sess_data = load_loop_session(sess_id)
        self.assertIsNotNone(sess_data)
        sess_data["status"] = "running"
        sess_data["research_brief"] = "# Research Brief\n\nVerified Redis contracts."
        sess_data["tasks"] = [
            {"id": "task-1", "title": "Draft Lock", "status": "completed", "role": "dev"}
        ]
        sess_data["verification_certificate"] = "APPROVED by Auto-Judge"
        sess_data["attempts"] = 1
        sess_data["github_issue"] = {"issue_number": 101, "url": "https://github.com/test/issues/101"}
        save_loop_session(sess_data)

        # 3. Load & Verify all tracked fields
        reloaded = load_loop_session(sess_id)
        self.assertEqual(reloaded["session_id"], sess_id)
        self.assertEqual(reloaded["status"], "running")
        self.assertEqual(reloaded["research_brief"], "# Research Brief\n\nVerified Redis contracts.")
        self.assertEqual(len(reloaded["tasks"]), 1)
        self.assertEqual(reloaded["verification_certificate"], "APPROVED by Auto-Judge")
        self.assertEqual(reloaded["attempts"], 1)
        self.assertEqual(reloaded["github_issue"]["issue_number"], 101)

        # 4. List loop sessions
        sessions_list = list_loop_sessions()
        matched = [s for s in sessions_list if s["id"] == sess_id or s["session_id"] == sess_id]
        self.assertEqual(len(matched), 1)
        self.assertEqual(matched[0]["has_github_issue"], True)
        self.assertEqual(matched[0]["has_certificate"], True)

        # 5. Rename loop session
        rename_loop_session(sess_id, "Renamed Distributed Lock Loop")
        renamed = load_loop_session(sess_id)
        self.assertEqual(renamed["title"], "Renamed Distributed Lock Loop")

        # 6. Delete loop session
        delete_loop_session(sess_id)
        deleted = load_loop_session(sess_id)
        self.assertIsNone(deleted)

    def test_loop_session_selection(self):
        sess1 = create_new_loop_session(title="Loop Session Alpha", goal="Goal Alpha")
        sess2 = create_new_loop_session(title="Loop Session Beta", goal="Goal Beta")
        
        # Select session 1
        state1 = select_loop_session(sess1["id"])
        self.assertEqual(state1["id"], sess1["id"])
        self.assertEqual(state1["goal"], "Goal Alpha")

        # Select session 2
        state2 = select_loop_session(sess2["id"])
        self.assertEqual(state2["id"], sess2["id"])
        self.assertEqual(state2["goal"], "Goal Beta")

        # Cleanup
        delete_loop_session(sess1["id"])
        delete_loop_session(sess2["id"])

    def test_two_way_advisor_and_loop_linking(self):
        # 1. Create Advisor Session
        adv_sess = create_new_session(title="Architecture Chat on Caching")
        adv_id = adv_sess["id"]

        # 2. Create Loop Session
        loop_sess = create_new_loop_session(title="Loop Caching", goal="Build Cache")
        loop_id = loop_sess["id"]

        # 3. Link them two-way
        link_advisor_and_loop_sessions(adv_id, loop_id)

        # 4. Verify advisor session has loop link
        adv_loaded = load_session(adv_id)
        self.assertIn(loop_id, adv_loaded.get("linked_loop_sessions", []))
        self.assertEqual(adv_loaded.get("last_loop_session_id"), loop_id)

        # 5. Verify loop session has advisor link
        loop_loaded = load_loop_session(loop_id)
        self.assertEqual(loop_loaded.get("advisor_session_id"), adv_id)

        # Cleanup
        delete_session(adv_id)
        delete_loop_session(loop_id)

    def test_advisor_to_loop_transfer_custom_goal(self):
        # 1. Create Advisor Session with conversation
        adv_sess = create_new_session(title="Token Bucket Rate Limiting")
        adv_id = adv_sess["id"]
        save_session_turn(adv_id, {
            "prompt": "How should we design token bucket rate limiting middleware in FastAPI?",
            "answer": "Use Redis Redis-Cell or atomic Lua script with sliding window.",
            "duration": 1.1,
            "timestamp": int(time.time() * 1000)
        })

        with patch("swarm.loop_engine._thread_worker"):
            # 2. Transfer with custom goal override
            result = transfer_advisor_to_loop(
                session_id=adv_id,
                custom_goal="Build Token Bucket Rate Limiter with Lua Scripts & Unit Tests",
                auto_start=True,
                repo_path="/test/repo"
            )

            self.assertTrue(result["success"])
            self.assertEqual(result["goal"], "Build Token Bucket Rate Limiter with Lua Scripts & Unit Tests")
            self.assertEqual(result["advisor_session_id"], adv_id)
            
            loop_id = result["loop_session_id"]
            self.assertTrue(loop_id.startswith("loop_"))

            # Verify two-way linking
            adv_loaded = load_session(adv_id)
            self.assertIn(loop_id, adv_loaded.get("linked_loop_sessions", []))

            loop_loaded = load_loop_session(loop_id)
            self.assertEqual(loop_loaded["advisor_session_id"], adv_id)
            self.assertEqual(loop_loaded["goal"], "Build Token Bucket Rate Limiter with Lua Scripts & Unit Tests")

            # Cleanup
            delete_session(adv_id)
            delete_loop_session(loop_id)

    def test_advisor_to_loop_transfer_synthesis_flow(self):
        adv_sess = create_new_session(title="Database Sharding Architecture")
        adv_id = adv_sess["id"]
        save_session_turn(adv_id, {
            "prompt": "Can we implement consistent hashing shard router?",
            "answer": "Yes, implement virtual nodes ring with MurmurHash3.",
            "duration": 0.8,
            "timestamp": int(time.time() * 1000)
        })

        async def run_test():
            with patch("swarm.loop_engine.query_gemini", new_callable=AsyncMock) as mock_gemini, \
                 patch("swarm.loop_engine._thread_worker"):
                mock_gemini.return_value = "Implement Consistent Hashing Shard Router with Virtual Nodes"
                
                result = await async_transfer_advisor_to_loop(
                    session_id=adv_id,
                    custom_goal="",
                    auto_start=False,
                    repo_path="/test/repo"
                )

                self.assertTrue(result["success"])
                self.assertIn("Consistent Hashing", result["goal"])
                self.assertEqual(result["advisor_session_id"], adv_id)
                self.assertFalse(result["auto_started"])

                loop_id = result["loop_session_id"]
                loop_loaded = load_loop_session(loop_id)
                self.assertIsNotNone(loop_loaded)
                self.assertEqual(loop_loaded["advisor_session_id"], adv_id)

                delete_session(adv_id)
                delete_loop_session(loop_id)

        asyncio.run(run_test())

if __name__ == "__main__":
    unittest.main()

import json
import urllib.request
import socketserver
from http.server import HTTPServer
import threading
from swarm.server import SwarmHandler

class TestServerLoopEndpoints(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Start server on ephemeral port (port 0)
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

    def test_server_loop_sessions_and_transfer_api(self):
        # 1. GET /api/loop/sessions
        status, sessions = self._req("/api/loop/sessions")
        self.assertEqual(status, 200)
        self.assertIsInstance(sessions, list)

        # 2. POST /api/loop/sessions/new
        status, new_sess = self._req("/api/loop/sessions/new", method="POST", data={
            "title": "API Test Loop",
            "goal": "Verify API Endpoints",
            "repo_path": "/test/api_repo"
        })
        self.assertEqual(status, 200)
        sess_id = new_sess["id"]
        self.assertTrue(sess_id.startswith("loop_"))

        # 3. GET /api/loop/sessions/{id}
        status, loaded = self._req(f"/api/loop/sessions/{sess_id}")
        self.assertEqual(status, 200)
        self.assertEqual(loaded["goal"], "Verify API Endpoints")

        # 4. POST /api/loop/sessions/{id}/select
        status, sel_res = self._req(f"/api/loop/sessions/{sess_id}/select", method="POST", data={})
        self.assertEqual(status, 200)
        self.assertTrue(sel_res["success"])
        self.assertEqual(sel_res["session_id"], sess_id)

        # 5. POST /api/advisor/transfer_to_loop
        with patch("swarm.loop_engine.query_gemini", new_callable=AsyncMock) as mock_gemini, \
             patch("swarm.loop_engine._thread_worker"):
            mock_gemini.return_value = "API Transferred Feature Goal"
            status, transfer_res = self._req("/api/advisor/transfer_to_loop", method="POST", data={
                "session_id": "",
                "custom_goal": "Direct API Transfer Goal",
                "auto_start": False,
                "repo_path": "/test/api_repo"
            })
            self.assertEqual(status, 200)
            self.assertTrue(transfer_res["success"])
            self.assertEqual(transfer_res["goal"], "Direct API Transfer Goal")
            
            # Clean up transferred session
            transferred_id = transfer_res["loop_session_id"]
            delete_loop_session(transferred_id)

        # 6. POST /api/loop/sessions/rename
        status, rename_res = self._req("/api/loop/sessions/rename", method="POST", data={
            "id": sess_id,
            "title": "Renamed API Loop"
        })
        self.assertEqual(status, 200)
        self.assertEqual(rename_res["status"], "renamed")

        # 7. POST /api/loop/sessions/delete
        status, del_res = self._req("/api/loop/sessions/delete", method="POST", data={
            "id": sess_id
        })
        self.assertEqual(status, 200)
        self.assertEqual(del_res["status"], "deleted")
