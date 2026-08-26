"""
Orchestrator honesty tests.

The Qwen consensus oracle must never fabricate a "verified" verdict when it did
not actually run. Failures (missing script, non-executable, exec error) must be
reported with the ORACLE-UNAVAILABLE sentinel so the UI and loop don't mistake a
fallback notice for a real adversarial review.
"""

import asyncio
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import swarm.orchestrator as orch
from swarm.orchestrator import query_qwen_web, QWEN_UNAVAILABLE_PREFIX


class TestOracleSafety(unittest.TestCase):
    def test_missing_script_reports_unavailable(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "does_not_exist.sh"
            with patch.object(orch, "QWEN_ORACLE_SCRIPT", missing):
                # Also ensure the home-dir fallback path doesn't exist.
                with patch("pathlib.Path.home", return_value=Path(tmp)):
                    out = asyncio.run(query_qwen_web("is 2+2=5?"))
        self.assertTrue(out.startswith(QWEN_UNAVAILABLE_PREFIX))
        self.assertNotIn("verified", out.lower())

    def test_non_executable_script_reports_unavailable(self):
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp) / "qwen_oracle.sh"
            script.write_text("#!/bin/bash\necho hi\n", encoding="utf-8")
            script.chmod(0o644)  # readable but NOT executable
            with patch.object(orch, "QWEN_ORACLE_SCRIPT", script):
                with patch("pathlib.Path.home", return_value=Path(tmp)):
                    out = asyncio.run(query_qwen_web("ping"))
        self.assertTrue(out.startswith(QWEN_UNAVAILABLE_PREFIX))
        self.assertIn("executable", out.lower())

    def test_executable_script_output_is_returned_verbatim(self):
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp) / "qwen_oracle.sh"
            script.write_text("#!/bin/bash\necho 'ADVERSARIAL VERDICT: looks fine'\n", encoding="utf-8")
            script.chmod(0o755)
            with patch.object(orch, "QWEN_ORACLE_SCRIPT", script):
                out = asyncio.run(query_qwen_web("review this"))
        self.assertIn("ADVERSARIAL VERDICT", out)
        self.assertFalse(out.startswith(QWEN_UNAVAILABLE_PREFIX))


if __name__ == "__main__":
    unittest.main()
