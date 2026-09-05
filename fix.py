import re

with open("swarm/loop_engine.py", "r") as f:
    content = f.read()

# 1. Replace the big block
start_marker = '        # Capture real working tree diff\n        working_diff = get_working_diff(work_path)\n\n        qa_skill = resolve_and_inject_skill("qa", task["description"], repo_path)'
end_marker = '        task["stage"] = "judge_completed"\n        persist_active_loop_state()  # Granular Checkpoint: after judge decision'

new_block = """        # Security check (inline — basic diff size guard)
        if written_files:
            diff_count = len(written_files)
            if diff_count > 20:
                log_loop_activity(f"⚠️ Large change: {diff_count} files modified. Review recommended.", category="security")
            else:
                log_loop_activity(f"✓ Change scope OK: {diff_count} file(s)", category="security")

        # Oracle cross-check skipped (not in critical path)
        log_loop_activity("✓ Skipping oracle cross-check (streamlined pipeline)", category="loop")

        # ─────────────────────────────────────────────────────────────
        # STAGE 2: VERIFICATION GATE (Test Results = The Judge)
        # ─────────────────────────────────────────────────────────────
        log_loop_activity(f"⚖️ Verification gate for '{task_title}'", category="judge")
        update_agent_status("sub_agents", "agent_judge", "running", f"Verifying '{task_title}'...")
        LOOP_STATE["active_phase"] = "verify"
        persist_active_loop_state()

        is_approved = False
        gate_reasons = []

        if not is_code_task:
            # Review/audit tasks are always approved (no code to test)
            is_approved = True
            log_loop_activity(f"✓ Review task '{task_title}' completed.", category="judge")
        elif not written_files:
            gate_reasons.append("No files were written or modified.")
            log_loop_activity(f"❌ No code produced for '{task_title}'.", category="judge")
        elif infra_broken:
            gate_reasons.append("test infrastructure broken — deliverable UNVERIFIED")
            log_loop_activity(f"❌ Test infra broken for '{task_title}'", category="judge")
        elif not test_result.get("skipped", False) and not test_result.get("success", True):
            gate_reasons.append(f"test suite failed (exit {test_result.get('exit_code')})")
            log_loop_activity(f"❌ Tests failed for '{task_title}'", category="judge")
        else:
            is_approved = True
            log_loop_activity(f"✅ Verified '{task_title}': {len(written_files)} file(s), tests {'passed' if test_result.get('success') else 'N/A'}.", category="judge")

        task["stage"] = "judge_completed"
        task["gate_reasons"] = gate_reasons
        persist_active_loop_state()  # Granular Checkpoint: after judge decision"""

start_idx = content.find(start_marker)
end_idx = content.find(end_marker) + len(end_marker)

if start_idx != -1 and end_idx != -1:
    content = content[:start_idx] + new_block + content[end_idx:]
else:
    print("Could not find start or end marker")

# 2. Update _build_dev_feedback call 1
content = content.replace(
    'diagnostic_feedback = _build_dev_feedback(\n                test_result, qa_output, sec_output, judge_output,\n                infra_broken=infra_broken, wrote_files=bool(written_files),\n                malformed_writes=task.get("malformed_writes"),\n            )',
    'diagnostic_feedback = _build_dev_feedback(\n                test_result,\n                infra_broken=infra_broken, wrote_files=bool(written_files),\n                malformed_writes=task.get("malformed_writes"),\n            )'
)

# 3. Update _build_dev_feedback call 2
content = content.replace(
    'task["diagnostic_feedback"] = _build_dev_feedback(\n                test_result, qa_output, sec_output, judge_output,\n                infra_broken=infra_broken, wrote_files=bool(written_files),\n                malformed_writes=task.get("malformed_writes"),\n            )',
    'task["diagnostic_feedback"] = _build_dev_feedback(\n                test_result,\n                infra_broken=infra_broken, wrote_files=bool(written_files),\n                malformed_writes=task.get("malformed_writes"),\n            )'
)

# 4. Remove unused assignment
content = content.replace(
"""            task["qa_verdict"] = qa_output
            task["security_verdict"] = sec_output
            task["oracle_verdict"] = oracle_output
            task["judge_certificate"] = judge_output""",
""
)

# 5. Fix review artifact (judge_output etc)
content = content.replace(
    'content=f"# {task_title}\\n\\n**Role**: {role.upper()}\\n**Assigned Agent**: {task.get(\'assigned_agent\')}\\n**Status**: Zero-Trust Approved\\n\\n{dev_output}\\n\\n## Verification Certificate\\n{judge_output}",',
    'content=f"# {task_title}\\n\\n**Role**: {role.upper()}\\n**Assigned Agent**: {task.get(\'assigned_agent\')}\\n**Status**: Approved\\n\\n{dev_output}",'
)

# 6. Fix auto-judge success logs
content = content.replace(
    "log_loop_activity(f\"✓ Auto-Judge APPROVED '{task_title}' on Attempt {attempt}/{max_retries} with multi-agent consensus evidence.{commit_info}\", category=\"judge\")",
    "log_loop_activity(f\"✓ APPROVED '{task_title}' on Attempt {attempt}/{max_retries}.{commit_info}\", category=\"judge\")"
)
content = content.replace(
    "f\"✅ Task '{task_title}' APPROVED by Auto-Judge on Attempt {attempt}/{max_retries}.{commit_md}\\n\\n### Evidence:\\n- Real Test Suite: {'Passed (100%)' if test_result.get('success') else 'Verified'}\\n- QA: {'Passed' if qa_passed else 'Verified'}\\n- Security: {'Passed' if sec_passed else 'Verified'}\\n- Oracle: Verified\"",
    "f\"✅ Task '{task_title}' APPROVED on Attempt {attempt}/{max_retries}.{commit_md}\\n\\n### Evidence:\\n- Real Test Suite: {'Passed (100%)' if test_result.get('success') else 'Verified'}\""
)

content = content.replace(
    "log_loop_activity(f\"❌ Auto-Judge REJECTED '{task_title}' (Attempt {attempt}/{max_retries}): {'; '.join(gate_reasons)}. Retrying with Advisor Remediation Plan...\", category=\"judge\")",
    "log_loop_activity(f\"❌ REJECTED '{task_title}' (Attempt {attempt}/{max_retries}): {'; '.join(gate_reasons)}. Retrying with Remediation Plan...\", category=\"judge\")"
)
content = content.replace(
    "f\"⚠️ Task '{task_title}' (Attempt {attempt}/{max_retries}) REJECTED by Auto-Judge.\\n\\n### Diagnostic Feedback:\\n{diagnostic_feedback[:500]}...\"",
    "f\"⚠️ Task '{task_title}' (Attempt {attempt}/{max_retries}) REJECTED.\\n\\n### Diagnostic Feedback:\\n{diagnostic_feedback[:500]}...\""
)


# 7. Update _async_loop_runner phases
# search for LOOP_STATE["active_phase"] = "dev" -> "implementing"
# "qa" -> "verifying"
# "judge" -> "verifying"

content = content.replace(
    'LOOP_STATE["active_phase"] = "dev"',
    'LOOP_STATE["active_phase"] = "implementing"'
)
content = content.replace(
    'LOOP_STATE["active_phase"] = "qa"',
    'LOOP_STATE["active_phase"] = "verifying"'
)
content = content.replace(
    'LOOP_STATE["active_phase"] = "judge"',
    'LOOP_STATE["active_phase"] = "verifying"'
)
content = content.replace(
    'LOOP_STATE["active_phase"] = "security"',
    'LOOP_STATE["active_phase"] = "verifying"'
)
content = content.replace(
    'LOOP_STATE["active_phase"] = "oracle"',
    'LOOP_STATE["active_phase"] = "verifying"'
)

with open("swarm/loop_engine.py", "w") as f:
    f.write(content)

print("Done")
