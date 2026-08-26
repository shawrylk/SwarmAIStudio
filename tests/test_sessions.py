"""
Unit Tests for Multi-Chat Sessions Persistence
"""

import unittest
import time
from swarm.sessions import create_new_session, list_sessions, load_session, save_session_turn, delete_session

class TestSessions(unittest.TestCase):
    def test_session_lifecycle(self):
        # 1. Create
        sess = create_new_session(title="Test Auto Session")
        sess_id = sess["id"]
        self.assertTrue(sess_id.startswith("sess_"))

        # 2. Save Turn
        turn = {
            "prompt": "Test query",
            "answer": "Test answer",
            "duration": 1.2,
            "timestamp": int(time.time() * 1000)
        }
        save_session_turn(sess_id, turn)

        # 3. Load & Verify
        loaded = load_session(sess_id)
        self.assertEqual(len(loaded["messages"]), 1)
        self.assertEqual(loaded["messages"][0]["prompt"], "Test query")

        # 4. Clean up
        delete_session(sess_id)

if __name__ == "__main__":
    unittest.main()
