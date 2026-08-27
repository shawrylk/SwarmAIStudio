"""
Regression tests for the autonomous-loop failures observed in the
DeltaProject and BankFlow runs (loop_1787745868_a5914c, loop_1787746609_3966b9).

Each test pins one real defect:
  * a bare `tests/` dir made a .NET repo look like a Python project, so
    `unittest discover` ran instead of `dotnet test`;
  * that runner found one leftover placeholder test and reported
    "Ran 3 tests ... OK", which the loop presented as real verification of C#
    that never compiled;
  * an environment failure (`ModuleNotFoundError: pytest`) was fed back to the
    dev agent as a "MUST FIX" diagnostic, derailing it into emitting
    `bash(pip install pytest)` — a call this harness cannot serve — so it never
    wrote the feature;
  * when retries ran out the task was still marked "completed", committed, and
    merged with qa_passed=False.
"""

import asyncio
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, AsyncMock

from swarm.git_engine import (
    detect_project_test_runner,
    classify_test_failure,
    detect_vacuous_pass,
    check_runner_covers_deliverable,
    resolve_default_branch,
    run_git,
)
from swarm.loop_engine import (
    _parse_verdict,
    _parse_decision,
    _build_dev_feedback,
    _describe_unservable_tool_calls,
    execute_zero_trust_task,
)


class TestRunnerDetection(unittest.TestCase):
    def test_dotnet_repo_with_bare_tests_dir_is_not_python(self):
        """A .NET solution whose tests/ holds C# projects must not select a Python runner."""
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)
            (p / "DeltaProject.sln").write_text("Microsoft Visual Studio Solution File")
            (p / "tests" / "DeltaProject.Domain.Tests").mkdir(parents=True)
            (p / "tests" / "DeltaProject.Domain.Tests" / "FishTests.cs").write_text("// tests")

            runner = detect_project_test_runner(str(p))
            self.assertIsNotNone(runner)
            self.assertNotIn(runner["runner"], ("pytest", "python_unittest"))

    def test_python_detection_requires_real_test_file(self):
        """A directory literally named tests/ with no .py test files is not a Python project."""
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)
            (p / "tests").mkdir()
            (p / "tests" / "readme.md").write_text("no tests here")
            self.assertIsNone(detect_project_test_runner(str(p)))

    def test_python_repo_with_real_test_file_is_detected(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)
            (p / "tests").mkdir()
            (p / "tests" / "test_thing.py").write_text("import unittest\n")
            runner = detect_project_test_runner(str(p))
            self.assertIsNotNone(runner)
            self.assertIn(runner["runner"], ("pytest", "python_unittest"))

    def test_all_pytest_tests_without_pytest_installed_flags_dependency(self):
        """Tests that all import pytest, with pytest absent, must not be run under unittest."""
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)
            (p / "tests").mkdir()
            (p / "tests" / "test_a.py").write_text("import pytest\n\ndef test_a():\n    assert True\n")
            with patch("swarm.git_engine.shutil.which", return_value=None), \
                 patch("swarm.git_engine._module_importable", return_value=False):
                runner = detect_project_test_runner(str(p))
            self.assertEqual(runner.get("missing_dependency"), "pytest")


class TestVerificationHonesty(unittest.TestCase):
    def test_zero_test_pass_is_not_verification(self):
        res = detect_vacuous_pass({
            "success": True, "skipped": False, "exit_code": 0,
            "runner": "unittest", "output": "Ran 0 tests in 0.000s\n\nOK",
        })
        self.assertFalse(res["success"])
        self.assertEqual(res["failure_kind"], "infra")
        self.assertTrue(res["vacuous"])

    def test_python_runner_cannot_verify_csharp_deliverable(self):
        """The exact DeltaProject deception: 'Ran 3 tests OK' while the .cs never compiled."""
        res = check_runner_covers_deliverable(
            {"success": True, "skipped": False, "runner": "unittest",
             "output": "Ran 3 tests in 0.000s\n\nOK"},
            ["src/DeltaProject.Application/GameSessionNode.cs"],
        )
        self.assertFalse(res["success"])
        self.assertTrue(res["coverage_mismatch"])

    def test_matching_language_still_passes(self):
        res = check_runner_covers_deliverable(
            {"success": True, "skipped": False, "runner": "unittest",
             "output": "Ran 3 tests\n\nOK"},
            ["src/thing.py"],
        )
        self.assertTrue(res["success"])

    def test_doc_only_deliverable_does_not_trip_coverage_guard(self):
        res = check_runner_covers_deliverable(
            {"success": True, "skipped": False, "runner": "unittest", "output": "Ran 3 tests\n\nOK"},
            ["README.md", "notes.txt"],
        )
        self.assertTrue(res["success"])


class TestFailureClassification(unittest.TestCase):
    def test_missing_module_is_infrastructure_not_code(self):
        res = classify_test_failure({
            "success": False, "skipped": False, "exit_code": 1,
            "output": "ImportError: Failed to import test module: test_greet\n"
                      "ModuleNotFoundError: No module named 'pytest'",
        })
        self.assertEqual(res["failure_kind"], "infra")

    def test_timeout_is_infrastructure(self):
        res = classify_test_failure({
            "success": False, "skipped": False, "exit_code": 124,
            "output": "Test execution timed out after 60s",
        })
        self.assertEqual(res["failure_kind"], "infra")

    def test_real_assertion_failure_is_code(self):
        res = classify_test_failure({
            "success": False, "skipped": False, "exit_code": 1,
            "output": "FAILED tests/test_x.py::test_y - AssertionError: 3 != 4",
        })
        self.assertEqual(res["failure_kind"], "code")

    def test_infra_trace_is_withheld_from_dev_feedback(self):
        """Handing the dev agent a missing-dependency trace is what caused the pip-install loop."""
        fb = _build_dev_feedback(
            {"failure_kind": "infra", "infra_reason": "pytest is not installed on the host.",
             "output": "ModuleNotFoundError: No module named 'pytest'"},
            qa_output="VERDICT: FAILED", sec_output="VERDICT: FAILED",
            judge_output="DECISION: REJECTED", infra_broken=True, wrote_files=True,
        )
        self.assertNotIn("ModuleNotFoundError", fb)
        self.assertIn("NOT YOUR JOB", fb)

    def test_code_trace_is_forwarded_to_dev(self):
        fb = _build_dev_feedback(
            {"failure_kind": "code", "output": "AssertionError: 3 != 4"},
            qa_output="VERDICT: FAILED", sec_output="VERDICT: PASSED",
            judge_output="DECISION: REJECTED", infra_broken=False, wrote_files=True,
        )
        self.assertIn("AssertionError", fb)


class TestVerdictParsing(unittest.TestCase):
    def test_unservable_tool_call_is_not_a_pass(self):
        out = "<|tool_call_start|>[read_file(path='/x/y.py')]<|tool_call_end|>"
        self.assertFalse(_parse_verdict(out))
        self.assertFalse(_parse_decision(out))

    def test_prose_mentioning_passed_is_not_a_verdict(self):
        self.assertFalse(_parse_verdict("The security audit passed without issue."))

    def test_explicit_verdicts_are_honoured(self):
        self.assertTrue(_parse_verdict("analysis...\nVERDICT: PASSED"))
        self.assertFalse(_parse_verdict("analysis...\nVERDICT: FAILED (Reason: x)"))

    def test_approved_certificate_mentioning_failure_still_approves(self):
        """The old `"FAILED" not in output` scan made approval near-impossible."""
        self.assertTrue(_parse_decision("DECISION: APPROVED (Certificate: no failed tests remain)"))

    def test_unservable_calls_are_named_back_to_the_model(self):
        desc = _describe_unservable_tool_calls(
            "[bash(command='pip install pytest'), read_file(path='a.py')]"
        )
        self.assertIn("bash", desc)
        self.assertIn("read_file", desc)


class TestBranchTargetResolution(unittest.TestCase):
    def test_leftover_swarm_branch_is_never_the_integration_target(self):
        """The DeltaProject run merged into swarm/loop-1787743921 instead of main."""
        import subprocess

        def git(*args):
            # run_git() refuses a directory that is not yet a repo, so bootstrap
            # with subprocess and use run_git only once .git exists.
            subprocess.run(["git", "-C", td, *args], capture_output=True, text=True, check=False)

        with tempfile.TemporaryDirectory() as td:
            subprocess.run(["git", "init", "-b", "main", td], capture_output=True, check=False)
            (Path(td) / "f.txt").write_text("x")
            git("add", "-A")
            git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-m", "init")
            git("checkout", "-b", "swarm/loop-999")
            self.assertEqual(run_git(td, ["branch", "--show-current"])["stdout"], "swarm/loop-999")
            self.assertEqual(resolve_default_branch(td), "main")


class TestGateBlocksFabricatedApproval(unittest.TestCase):
    def test_exhausted_retries_fail_instead_of_reporting_completed(self):
        """Retries ran out with qa_passed False, yet the task was marked completed and merged."""
        task = {
            "id": "task-gate-1", "order": 1, "title": "Never Passes",
            "role": "dev", "description": "impl", "acceptance_criteria": "tests pass",
            "status": "pending", "attempts": 0, "advisor_consultations": [],
        }

        async def mock_slot(prompt, system="", **kwargs):
            pu = prompt.upper()
            if "SURGICAL CODE DRAFTSMAN" in pu:
                return "<|tool_call_start|>[write(path='src/a.py', content='x = 1\\n')]<|tool_call_end|>"
            if "ZERO-TRUST QA MANDATE" in pu:
                return "VERDICT: FAILED (Reason: missing coverage)"
            if "ZERO-TRUST SECURITY MANDATE" in pu:
                return "VERDICT: PASSED"
            if "AUTONOMOUS SWARM AUTO-JUDGE" in pu:
                return "DECISION: REJECTED (Diagnostics: fix coverage)"
            return "OK"

        async def run():
            with patch("swarm.loop_engine.query_local_slot", side_effect=mock_slot), \
                 patch("swarm.loop_engine.query_qwen_web", new_callable=AsyncMock, return_value="ok"), \
                 patch("swarm.loop_engine.ping_lead_advisor", new_callable=AsyncMock, return_value="g"), \
                 patch("swarm.loop_engine.commit_changes") as mock_commit:
                out = await execute_zero_trust_task(
                    task, repo_block="", repo_path="", research_brief="", github_issue_num=None
                )
                return out, mock_commit

        result, mock_commit = asyncio.run(run())
        self.assertEqual(result["status"], "failed")
        self.assertTrue(result.get("failure_reasons"))
        mock_commit.assert_not_called()

    def test_dev_producing_no_files_never_reaches_approval(self):
        """DeltaProject task-4 emitted read_file() calls, wrote nothing, and was 'completed'."""
        task = {
            "id": "task-gate-2", "order": 1, "title": "Inspection Only",
            "role": "review", "description": "audit", "acceptance_criteria": "clean",
            "status": "pending", "attempts": 0, "advisor_consultations": [],
        }

        async def mock_slot(prompt, system="", **kwargs):
            pu = prompt.upper()
            if "SURGICAL CODE DRAFTSMAN" in pu or "ZERO FILES WRITTEN" in prompt.upper():
                return "<|tool_call_start|>[read_file(path='/repo/x.cs')]<|tool_call_end|>"
            if "ZERO-TRUST QA MANDATE" in pu:
                return "VERDICT: PASSED"
            if "ZERO-TRUST SECURITY MANDATE" in pu:
                return "VERDICT: PASSED"
            if "AUTONOMOUS SWARM AUTO-JUDGE" in pu:
                return "DECISION: APPROVED (Certificate: looks fine)"
            return "OK"

        async def run():
            with patch("swarm.loop_engine.query_local_slot", side_effect=mock_slot), \
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


if __name__ == "__main__":
    unittest.main()


class TestMissingToolchainIsNotASilentPass(unittest.TestCase):
    def test_dotnet_repo_without_dotnet_reports_missing_dependency(self):
        """"No runner detected" returns skipped=True, which the gate treats as a pass."""
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)
            (p / "App.sln").write_text("solution")
            with patch("swarm.git_engine.shutil.which", return_value=None):
                runner = detect_project_test_runner(str(p))
            self.assertIsNotNone(runner)
            self.assertEqual(runner.get("missing_dependency"), "dotnet")

    def test_missing_dependency_run_is_infra_failure_not_skip(self):
        from swarm.git_engine import run_test_suite
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)
            (p / "App.sln").write_text("solution")
            with patch("swarm.git_engine.shutil.which", return_value=None):
                res = classify_test_failure(run_test_suite(str(p)))
            self.assertFalse(res["success"])
            self.assertFalse(res["skipped"])
            self.assertEqual(res["failure_kind"], "infra")


class TestDotnetTargetSelection(unittest.TestCase):
    def test_explicit_target_when_folder_has_sln_and_stray_csproj(self):
        """Bare `dotnet test` fails MSB1011 here — DeltaProject has both files."""
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "DeltaProject"
            p.mkdir()
            (p / "DeltaProject.sln").write_text("solution")
            (p / "DeltaProject.Tools.csproj").write_text("<Project/>")
            runner = detect_project_test_runner(str(p))
            self.assertEqual(runner["command"], ["dotnet", "test", "DeltaProject.sln"])

    def test_solution_named_after_directory_is_preferred(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "MyApp"
            p.mkdir()
            (p / "Aaa.Other.sln").write_text("s")
            (p / "MyApp.sln").write_text("s")
            runner = detect_project_test_runner(str(p))
            self.assertEqual(runner["command"][-1], "MyApp.sln")

    def test_single_csproj_without_solution_is_targeted(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)
            (p / "Only.csproj").write_text("<Project/>")
            runner = detect_project_test_runner(str(p))
            self.assertEqual(runner["command"], ["dotnet", "test", "Only.csproj"])


class TestCodeSignalsBeatInfraPatterns(unittest.TestCase):
    def test_csharp_compile_errors_are_code_failures(self):
        """These must reach the dev agent; classifying them infra would withhold them."""
        res = classify_test_failure({
            "success": False, "skipped": False, "exit_code": 1,
            "output": "src/X.cs(6,15): error CS0101: The namespace already contains a definition\n"
                      "src/Y.cs(20,19): error CS0246: The type or namespace name could not be found",
        })
        self.assertEqual(res["failure_kind"], "code")

    def test_msbuild_target_ambiguity_is_infra(self):
        res = classify_test_failure({
            "success": False, "skipped": False, "exit_code": 1,
            "output": "MSBUILD : error MSB1011: Specify which project or solution file to use",
        })
        self.assertEqual(res["failure_kind"], "infra")

    def test_compile_error_wins_over_incidental_infra_substring(self):
        res = classify_test_failure({
            "success": False, "skipped": False, "exit_code": 1,
            "output": "warning: no such file or directory: stale.cs\n"
                      "src/X.cs(1,1): error CS1002: ; expected",
        })
        self.assertEqual(res["failure_kind"], "code")


class TestForeignAbsolutePathHandling(unittest.TestCase):
    """A run wrote 21 files into <repo>/home/shawry/Documents/... because any
    absolute path that did not resolve inside the repo had its leading slash
    stripped, which then passed the containment check."""

    def test_recoverable_path_is_rebased_onto_the_real_directory(self):
        from swarm.git_engine import salvage_foreign_abs_path
        with tempfile.TemporaryDirectory() as td:
            r = Path(td)
            (r / "src" / "DeltaProject.Domain").mkdir(parents=True)
            self.assertEqual(
                salvage_foreign_abs_path("/home/u/Documents/GitHub/src/DeltaProject.Domain/X.cs", r),
                "src/DeltaProject.Domain/X.cs",
            )

    def test_unrecoverable_path_is_rejected_not_stripped(self):
        from swarm.git_engine import salvage_foreign_abs_path
        with tempfile.TemporaryDirectory() as td:
            r = Path(td)
            (r / "src" / "DeltaProject.Domain").mkdir(parents=True)
            # Real location is src/DeltaProject.Domain/; this path omits src/.
            self.assertIsNone(
                salvage_foreign_abs_path("/home/u/Documents/DeltaProject.Domain/FishState.cs", r))

    def test_bare_filename_is_never_accepted(self):
        from swarm.git_engine import salvage_foreign_abs_path
        with tempfile.TemporaryDirectory() as td:
            self.assertIsNone(salvage_foreign_abs_path("/tmp/orphan.cs", Path(td)))

    def test_result_is_always_contained_in_the_repo(self):
        from swarm.git_engine import salvage_foreign_abs_path
        with tempfile.TemporaryDirectory() as td:
            r = Path(td)
            for probe in ("/etc/passwd", "/../../etc/shadow", "/home/u/x/y.cs"):
                got = salvage_foreign_abs_path(probe, r)
                if got is not None:
                    self.assertFalse(Path(got).is_absolute())
                    (r / got).parent.mkdir(parents=True, exist_ok=True)
                    self.assertTrue(str((r / got).resolve()).startswith(str(r.resolve())))

    def test_writer_creates_no_bogus_nested_tree(self):
        from swarm.git_engine import extract_code_blocks_and_write
        with tempfile.TemporaryDirectory() as td:
            r = Path(td)
            (r / "src").mkdir()
            out = ("<|tool_call_start|>[write(path='/home/shawry/Documents/DeltaProject.Domain/Ghost.cs', "
                   "content='class Ghost {}')]<|tool_call_end|>")
            written = extract_code_blocks_and_write(str(r), out)
            self.assertEqual(written, [])
            self.assertFalse((r / "home").exists())
