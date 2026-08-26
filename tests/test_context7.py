"""
Unit Tests for Context7 Live Documentation & API Scout Sub-Agent
"""

import unittest
from unittest.mock import patch, MagicMock
from swarm.context7_engine import query_context7_library, query_context7_docs, fetch_latest_doc_context

class TestContext7Engine(unittest.TestCase):
    def test_query_context7_library(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="Title: FastMCP\nContext7-compatible library ID: /prefecthq/fastmcp\n", stderr="")
            res = query_context7_library("fastmcp")
            self.assertTrue(res["success"])
            self.assertIn("/prefecthq/fastmcp", res["output"])

    def test_query_context7_docs(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="## FastMCP Tools\nUse @mcp.tool() decorator.", stderr="")
            res = query_context7_docs("/prefecthq/fastmcp", "tools")
            self.assertTrue(res["success"])
            self.assertIn("@mcp.tool()", res["docs"])

    def test_fetch_latest_doc_context_pipeline(self):
        with patch("swarm.context7_engine.query_context7_library") as mock_lib, \
             patch("swarm.context7_engine.query_context7_docs") as mock_docs:
            
            mock_lib.return_value = {
                "success": True,
                "output": "1. Title: FastAPI\nContext7-compatible library ID: /tiangolo/fastapi\nDescription: Modern web framework"
            }
            mock_docs.return_value = {
                "success": True,
                "docs": "### Depends\nUse Depends() for route dependencies."
            }

            doc_context = fetch_latest_doc_context("fastapi", "route dependencies")
            self.assertIn("CONTEXT7 LATEST DOCS", doc_context)
            self.assertIn("Depends()", doc_context)

if __name__ == "__main__":
    unittest.main()
