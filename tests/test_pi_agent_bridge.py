"""
Tests for the Pi coding-agent bridge and the dev-stage engine switch.

The bridge exists to fix the defect behind the DeltaProject run: with a single
blind completion the dev model could not read a file before rewriting it, so
FishAI.cs went 380 -> 69 lines and GpuBoidSimulation.cs 188 -> 23. Pi gives the
same model a read tool.

run_pi_agent is mocked throughout — these tests cover wiring, parsing and
fallback, not the live agent.
"""

import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from swarm.pi_agent import parse_pi_events, _base_url_from_lfm, _relativize
from swarm.loop_engine import dev_engine_is_pi, _pi_written_files, execute_zero_trust_task
from swarm.git_engine import check_runner_covers_deliverable


def _events(cwd: str):
    """A realistic Pi JSONL stream: read, edit, then a summary."""
    f = f"{cwd}/inventory.py"
    return "\n".join(json.dumps(e) for e in [
        {"type": "session", "id": "abc", "cwd": cwd},
        {"type": "agent_start"},
        # message_update deltas must be ignored: a trivial task emitted 827 of them.
        {"type": "message_update", "message": {"role": "assistant", "content": [{"type": "text", "text": "partial junk"}]}},
        {"type": "message_end", "message": {"role": "assistant", "content": [
            {"type": "toolCall", "id": "1", "name": "read", "arguments": {"path": f}}]}},
        {"type": "message_end", "message": {"role": "assistant", "content": [
            {"type": "toolCall", "id": "2", "name": "edit", "arguments": {"path": f, "edits": []}}]}},
        {"type": "message_end", "message": {"role": "assistant", "content": [
            {"type": "text", "text": "Added restock_cost and left the existing functions unchanged."}]}},
        {"type": "agent_end"},
    ])


class TestEventParsing(unittest.TestCase):
    def test_extracts_final_text_tool_calls_and_written_files(self):
        with tempfile.TemporaryDirectory() as td:
            res = parse_pi_events(_events(td), td)
            self.assertEqual(res["files_written"], ["inventory.py"])
            self.assertEqual([t["name"] for t in res["tool_calls"]], ["read", "edit"])
            self.assertIn("restock_cost", res["text"])

    def test_streaming_deltas_do_not_become_the_final_text(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertNotIn("partial junk", parse_pi_events(_events(td), td)["text"])

    def test_read_only_tools_are_not_counted_as_writes(self):
        with tempfile.TemporaryDirectory() as td:
            stream = json.dumps({"type": "message_end", "message": {"role": "assistant", "content": [
                {"type": "toolCall", "id": "1", "name": "read", "arguments": {"path": f"{td}/a.py"}},
                {"type": "toolCall", "id": "2", "name": "bash", "arguments": {"command": "ls"}}]}})
            self.assertEqual(parse_pi_events(stream, td)["files_written"], [])

    def test_write_outside_the_repository_is_rejected(self):
        """extract_code_blocks_and_write enforced containment; the Pi path must too."""
        with tempfile.TemporaryDirectory() as td:
            stream = json.dumps({"type": "message_end", "message": {"role": "assistant", "content": [
                {"type": "toolCall", "id": "1", "name": "write", "arguments": {"path": "/etc/passwd"}}]}})
            res = parse_pi_events(stream, td)
            self.assertEqual(res["files_written"], [])
            self.assertEqual(res["rejected_paths"], ["/etc/passwd"])

    def test_malformed_lines_are_skipped(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(parse_pi_events("not json\n\n{broken", td)["files_written"], [])

    def test_base_url_derivation(self):
        self.assertEqual(_base_url_from_lfm("http://localhost:8034/v1/chat/completions"), "http://localhost:8034/v1")
        self.assertEqual(_base_url_from_lfm("http://h/v1/"), "http://h/v1")

    def test_relativize_confines_to_repo(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(_relativize(f"{td}/src/a.py", Path(td)), "src/a.py")
            self.assertIsNone(_relativize("/etc/shadow", Path(td)))


class TestEngineSelection(unittest.TestCase):
    def test_raw_engine_setting_disables_pi(self):
        with tempfile.TemporaryDirectory() as td:
            with patch("swarm.loop_engine.DEV_AGENT_ENGINE", "raw"):
                self.assertFalse(dev_engine_is_pi(td))

    def test_auto_uses_pi_when_cli_present(self):
        with tempfile.TemporaryDirectory() as td:
            with patch("swarm.loop_engine.DEV_AGENT_ENGINE", "auto"), \
                 patch("swarm.loop_engine.pi_available", return_value=True):
                self.assertTrue(dev_engine_is_pi(td))

    def test_auto_falls_back_when_cli_absent(self):
        with tempfile.TemporaryDirectory() as td:
            with patch("swarm.loop_engine.DEV_AGENT_ENGINE", "auto"), \
                 patch("swarm.loop_engine.pi_available", return_value=False):
                self.assertFalse(dev_engine_is_pi(td))

    def test_no_repo_means_no_pi(self):
        with patch("swarm.loop_engine.DEV_AGENT_ENGINE", "pi"), \
             patch("swarm.loop_engine.pi_available", return_value=True):
            self.assertFalse(dev_engine_is_pi(""))


class TestWrittenFileRecords(unittest.TestCase):
    def test_records_carry_real_sizes_from_disk(self):
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "a.py").write_text("x = 1\ny = 2\n")
            recs = _pi_written_files({"files_written": ["a.py"]}, td)
            self.assertEqual(recs[0]["path"], "a.py")
            self.assertEqual(recs[0]["lines"], 2)

    def test_records_feed_the_language_coverage_guard(self):
        """An empty list makes check_runner_covers_deliverable pass everything."""
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "Game.cs").write_text("public class Game {}")
            recs = _pi_written_files({"files_written": ["Game.cs"]}, td)
            res = check_runner_covers_deliverable(
                {"success": True, "skipped": False, "runner": "unittest", "output": "Ran 3 tests\nOK"},
                [r["path"] for r in recs],
            )
            self.assertFalse(res["success"])
            self.assertTrue(res["coverage_mismatch"])


class TestDevStageUsesPi(unittest.TestCase):
    def _task(self):
        return {"id": "t1", "order": 1, "title": "Add restock cost", "role": "dev",
                "description": "d", "acceptance_criteria": "a", "status": "pending",
                "attempts": 0, "advisor_consultations": []}

    async def _audits(self, prompt, system="", **kw):
        pu = prompt.upper()
        if "ZERO-TRUST QA MANDATE" in pu:
            return "VERDICT: PASSED"
        if "ZERO-TRUST SECURITY MANDATE" in pu:
            return "VERDICT: PASSED"
        if "AUTONOMOUS SWARM AUTO-JUDGE" in pu:
            return "DECISION: APPROVED (Certificate: ok)"
        return "OK"

    def test_pi_result_becomes_the_deliverable_without_double_writing(self):
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "inventory.py").write_text("def a():\n    return 1\n")
            pi_res = {"success": True, "error": "", "text": "Edited inventory.py",
                      "tool_calls": [{"name": "read", "path": "inventory.py"},
                                     {"name": "edit", "path": "inventory.py"}],
                      "files_written": ["inventory.py"], "rejected_paths": []}

            async def run():
                with patch("swarm.loop_engine.dev_engine_is_pi", return_value=True), \
                     patch("swarm.loop_engine.run_pi_agent", new_callable=AsyncMock, return_value=pi_res), \
                     patch("swarm.loop_engine.extract_code_blocks_and_write") as mock_extract, \
                     patch("swarm.loop_engine.query_local_slot", side_effect=self._audits), \
                     patch("swarm.loop_engine.query_qwen_web", new_callable=AsyncMock, return_value="ok"), \
                     patch("swarm.loop_engine.ping_lead_advisor", new_callable=AsyncMock, return_value="g"), \
                     patch("swarm.loop_engine.commit_changes", return_value={"success": True, "committed": True,
                                                                             "commit_hash": "h", "short_hash": "h"}):
                    out = await execute_zero_trust_task(self._task(), "", td, "brief", None)
                    return out, mock_extract

            task, mock_extract = asyncio.run(run())
            self.assertEqual(task["dev_engine"], "pi")
            self.assertEqual(task["files_written"], ["inventory.py"])
            # The fence/tool-call scraper must not also run, or files get written twice.
            mock_extract.assert_not_called()

    def test_pi_failure_falls_back_to_single_completion(self):
        """A Pi launch or timeout problem is not evidence about the deliverable."""
        with tempfile.TemporaryDirectory() as td:
            failed = {"success": False, "error": "pi exited 1", "text": "", "files_written": []}

            async def dev_or_audit(prompt, system="", **kw):
                if "SURGICAL CODE DRAFTSMAN" in prompt.upper():
                    return "<|tool_call_start|>[write(path='x.py', content='v = 1\\n')]<|tool_call_end|>"
                return await self._audits(prompt, system, **kw)

            async def run():
                with patch("swarm.loop_engine.dev_engine_is_pi", return_value=True), \
                     patch("swarm.loop_engine.run_pi_agent", new_callable=AsyncMock, return_value=failed), \
                     patch("swarm.loop_engine.query_local_slot", side_effect=dev_or_audit), \
                     patch("swarm.loop_engine.query_qwen_web", new_callable=AsyncMock, return_value="ok"), \
                     patch("swarm.loop_engine.ping_lead_advisor", new_callable=AsyncMock, return_value="g"), \
                     patch("swarm.loop_engine.commit_changes", return_value={"success": True, "committed": True,
                                                                             "commit_hash": "h", "short_hash": "h"}):
                    return await execute_zero_trust_task(self._task(), "", td, "brief", None)

            task = asyncio.run(run())
            self.assertIn("fallback", task["dev_engine"])
            self.assertEqual(task["files_written"], ["x.py"])
            self.assertTrue((Path(td) / "x.py").exists())


if __name__ == "__main__":
    unittest.main()


class TestMalformedWriteDetection(unittest.TestCase):
    """Observed live: the agent wrote a test file whose whole body was one line
    containing literal backslash-n, so pytest failed at collection. The gate
    caught it but the retry feedback never explained why."""

    def test_literal_escape_file_is_flagged(self):
        from swarm.pi_agent import detect_malformed_writes
        with tempfile.TemporaryDirectory() as td:
            body = ("import math\\nfrom src.flock import FlockSim\\n\\n"
                    "def test_x():\\n    assert True\\n" * 4)
            (Path(td) / "bad.py").write_text(body)
            self.assertEqual(detect_malformed_writes(td, ["bad.py"]), ["bad.py"])

    def test_normal_file_is_not_flagged(self):
        from swarm.pi_agent import detect_malformed_writes
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "ok.py").write_text("def f():\n    return 1\n" * 20)
            self.assertEqual(detect_malformed_writes(td, ["ok.py"]), [])

    def test_file_mentioning_newline_escape_in_a_string_is_not_flagged(self):
        from swarm.pi_agent import detect_malformed_writes
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "ok.py").write_text('SEP = "\\n"\n\ndef join(xs):\n    return SEP.join(xs)\n' * 6)
            self.assertEqual(detect_malformed_writes(td, ["ok.py"]), [])

    def test_feedback_names_the_corrupt_files(self):
        from swarm.loop_engine import _build_dev_feedback
        fb = _build_dev_feedback(
            {"failure_kind": "code", "output": "ERROR collecting src/test_flock.py"},
            qa_output="VERDICT: FAILED", sec_output="VERDICT: PASSED",
            judge_output="DECISION: REJECTED", infra_broken=False, wrote_files=True,
            malformed_writes=["src/test_flock.py"],
        )
        self.assertIn("LITERAL ESCAPE SEQUENCES", fb)
        self.assertIn("src/test_flock.py", fb)
