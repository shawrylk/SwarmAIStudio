"""
Unit Tests for Super-Orchestrator Multi-Engine Execution Bridge
"""

import unittest
import asyncio
from swarm.engine_bridge import (
    probe_all_backends,
    test_backend_connection as probe_backend_connection
)

class TestEngineBridge(unittest.TestCase):
    def test_probe_all_backends_discovers_engines(self):
        res = asyncio.run(probe_all_backends())
        self.assertEqual(res["total_count"], 5)
        self.assertGreaterEqual(res["active_count"], 3)
        
        backends = res["backends"]
        self.assertIn("claude_code", backends)
        self.assertIn("agy_gemini", backends)
        self.assertIn("context7_mcp", backends)
        self.assertIn("liquid_lfm", backends)
        self.assertIn("qwen_oracle", backends)

    def test_test_backend_connection_context7(self):
        res = asyncio.run(probe_backend_connection("context7_mcp"))
        self.assertEqual(res["backend"], "context7_mcp")
        self.assertTrue(res["success"])

if __name__ == "__main__":
    unittest.main()
