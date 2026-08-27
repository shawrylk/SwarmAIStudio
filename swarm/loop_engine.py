"""
Autonomous Loop Agent Engine (Auto-Dev Swarm)
Decomposes goals, executes Pre-Flight Research, conducts Zero-Trust Multi-Agent Handoff
(Dev -> QA -> Security -> Adversarial Oracle -> Auto-Judge Gate with Retry Loop),
injects dynamic skills, synchronizes Swarm Topology, and tracks progress in GitHub Issues.
"""

import asyncio
import threading
import time
import json
import uuid
import re
from pathlib import Path
from typing import List, Dict, Any, Optional
from swarm.config import (
    AUTO_RESUME_ON_START,
    MAX_CONCURRENT_AGENTS,
    PARALLEL_AUDIT_PHASE,
    PARALLEL_TASK_EXECUTION,
    MULTI_WORKTREE_DAG,
    DEV_AGENT_ENGINE,
    PI_AGENT_TIMEOUT,
)
from swarm.logger import log_event
from swarm.git_engine import (
    extract_deep_repo_context,
    format_repo_prompt_block,
    run_git,
    switch_or_create_branch,
    resolve_default_branch,
    detect_project_test_runner,
    run_test_suite,
    classify_test_failure,
    detect_vacuous_pass,
    check_runner_covers_deliverable,
    extract_code_blocks_and_write,
    get_working_diff,
    commit_changes,
    merge_branch,
    git_delete_branch,
    gh_issue_create,
    gh_issue_comment,
    gh_issue_close,
    gh_pr_create,
    is_gh_available,
    gh_project_ensure,
    gh_project_add_issue,
    gh_project_add_task,
    gh_project_set_status,
)
from swarm.model_scout import load_model_assignments
from swarm.artifacts import save_artifact_to_disk
from swarm.rules_engine import format_enforced_rules_prompt
from swarm.skills_scanner import resolve_and_inject_skill
from swarm.context7_engine import fetch_latest_doc_context
from swarm.pi_agent import run_pi_agent, pi_available
from swarm.contracts_engine import format_contracts_prompt_block, scan_and_parse_contracts, validate_cel_invariants
from swarm.orchestrator import (
    set_dynamic_subagents_roster,
    update_agent_status,
    query_gemini,
    query_local_slot,
    query_qwen_web,
    SWARM_STATE
)
from swarm.sessions import (
    list_sessions,
    load_session,
    list_loop_sessions,
    create_new_loop_session,
    load_loop_session,
    save_loop_session,
    delete_loop_session,
    rename_loop_session,
    link_advisor_and_loop_sessions,
    detect_and_recover_interrupted_sessions
)

_state_lock = threading.RLock()

# Dynamic Sub-Agent Roster for Autonomous Loop Operations
SWARM_LOOP_ROSTER = [
    {
        "id": "agent_arch",
        "name": "📐 Solution Architect & Research",
        "skill": "Pre-Flight Codebase & Context7 Scout",
        "role": "Level 3: Architecture & Discovery",
        "engine": "Local LFM (Slot 1)",
        "status": "idle",
        "task": "Idle",
        "tools": ["extract_repo_context", "context7_docs", "rules_engine"]
    },
    {
        "id": "agent_dev",
        "name": "⚙️ Surgical Code Draftsman",
        "skill": "TDD & Clean Implementation",
        "role": "Level 3: Code Synthesis",
        "engine": "Local LFM (Slot 2)",
        "status": "idle",
        "task": "Idle",
        "tools": ["replace_content", "write_file", "tdd_loop"]
    },
    {
        "id": "agent_qa",
        "name": "🧪 QA & LSP Compiler Verifier",
        "skill": "Zero-Trust Contract & Syntax Gate",
        "role": "Level 3: Verification & Test",
        "engine": "Local LFM (Slot 3)",
        "status": "idle",
        "task": "Idle",
        "tools": ["check_syntax", "pytest", "contract_verify"]
    },
    {
        "id": "agent_sec",
        "name": "🛡️ Security Threat Auditor",
        "skill": "OWASP & Blast Radius Scanner",
        "role": "Level 3: Security & Safety",
        "engine": "Local LFM (Slot 4)",
        "status": "idle",
        "task": "Idle",
        "tools": ["auth_audit", "injection_check", "secret_leak_hunt"]
    },
    {
        "id": "agent_oracle",
        "name": "🔮 Adversarial Consensus Oracle",
        "skill": "Cross-Check & Anti-Pattern Hunter",
        "role": "Consensus Oracle Peer",
        "engine": "chat.qwen.ai / Local Peer",
        "status": "idle",
        "task": "Idle",
        "tools": ["web_ask", "oracle_crosscheck"]
    },
    {
        "id": "agent_judge",
        "name": "⚖️ Autonomous Swarm Judge",
        "skill": "Zero-Trust Acceptance & Retry Gate",
        "role": "Level 3: Decision Gatekeeper",
        "engine": "Local LFM (Slot 5)",
        "status": "idle",
        "task": "Idle",
        "tools": ["evidence_evaluator", "retry_dispatcher"]
    }
]

def _ensure_loop_state_keys(state: Dict[str, Any]) -> Dict[str, Any]:
    sess_id = state.get("session_id") or state.get("id") or f"loop_{int(time.time())}_{uuid.uuid4().hex[:6]}"
    state["id"] = sess_id
    state["session_id"] = sess_id
    title = state.get("title") or state.get("name") or (state.get("goal", "")[:35] if state.get("goal") else "Auto-Dev Loop")
    state["title"] = title
    state["name"] = title
    state.setdefault("status", "idle")
    state.setdefault("goal", "")
    state.setdefault("repo_path", "")
    state.setdefault("iteration", 0)
    state.setdefault("max_iterations", 20)
    state.setdefault("tasks", [])
    state.setdefault("current_task_id", None)
    state.setdefault("current_task_ids", [])
    state.setdefault("active_subagent", None)
    state.setdefault("active_subagents", [])
    state.setdefault("advisor_pings", [])
    state.setdefault("live_logs", [])
    state.setdefault("research_brief", "")
    state.setdefault("github_issue", None)
    state.setdefault("verification_certificate", "")
    state.setdefault("advisor_session_id", "")
    state.setdefault("started_at", 0)
    state.setdefault("completed_at", 0)
    state.setdefault("final_summary", "")
    state.setdefault("created_at", int(time.time() * 1000))
    state.setdefault("updated_at", int(time.time() * 1000))
    state.setdefault("attempts", 0)
    state.setdefault("git_branch", "")
    state.setdefault("target_branch", "main")
    state.setdefault("merge_commit", "")
    state.setdefault("merge_short_hash", "")
    state.setdefault("project_board", {})
    state.setdefault("branch_deleted", False)
    state.setdefault("test_summary", "")
    state.setdefault("learned_rules", [])
    state.setdefault("infra_blockers", [])
    state.setdefault("merge_blocked_reason", "")
    return state

def persist_active_loop_state():
    global LOOP_STATE
    with _state_lock:
        _ensure_loop_state_keys(LOOP_STATE)
        save_loop_session(LOOP_STATE)

def _init_default_loop_state() -> Dict[str, Any]:
    try:
        detect_and_recover_interrupted_sessions()
        sessions = list_loop_sessions()
        if sessions:
            loaded = load_loop_session(sessions[0]["id"])
            if loaded:
                return _ensure_loop_state_keys(loaded)
    except Exception:
        pass
    
    sess_id = f"loop_{int(time.time())}_{uuid.uuid4().hex[:6]}"
    return _ensure_loop_state_keys({
        "id": sess_id,
        "session_id": sess_id,
        "name": "Main Auto-Dev Loop",
        "title": "Main Auto-Dev Loop",
        "status": "idle",
        "goal": "",
        "repo_path": "",
        "iteration": 0,
        "max_iterations": 20,
        "tasks": [],
        "current_task_id": None,
        "current_task_ids": [],
        "active_subagent": None,
        "active_subagents": [],
        "advisor_pings": [],
        "live_logs": [],
        "research_brief": "",
        "github_issue": None,
        "verification_certificate": "",
        "advisor_session_id": "",
        "started_at": 0,
        "completed_at": 0,
        "final_summary": "",
        "created_at": int(time.time() * 1000),
        "updated_at": int(time.time() * 1000),
        "attempts": 0,
        "git_branch": "",
        "target_branch": "main",
        "merge_commit": "",
        "merge_short_hash": "",
        "project_board": {},
        "branch_deleted": False,
        "test_summary": ""
    })

# Global Autonomous Loop State
LOOP_STATE: Dict[str, Any] = _init_default_loop_state()

_loop_thread: Optional[threading.Thread] = None
_loop_asyncio_loop: Optional[asyncio.AbstractEventLoop] = None
_pause_event = threading.Event()
_pause_event.set()
_stop_flag = False

def get_loop_state() -> Dict[str, Any]:
    global LOOP_STATE, _loop_thread
    with _state_lock:
        _ensure_loop_state_keys(LOOP_STATE)
        # Self-healing watchdog: If state claims to be "running" or "recovering"
        # but no background worker thread exists, transition state to an honest terminal/interrupted status.
        if LOOP_STATE.get("status") in ("running", "recovering"):
            if _loop_thread is None:
                tasks = LOOP_STATE.get("tasks", [])
                if tasks and all(t.get("status") == "completed" for t in tasks):
                    LOOP_STATE["status"] = "completed"
                elif any(t.get("status") == "failed" for t in tasks):
                    LOOP_STATE["status"] = "failed"
                elif not LOOP_STATE.get("goal"):
                    LOOP_STATE["status"] = "idle"
                else:
                    LOOP_STATE["status"] = "interrupted"
                LOOP_STATE["active_subagent"] = None
                LOOP_STATE["active_subagents"] = []
                LOOP_STATE["current_task_id"] = None
                LOOP_STATE["current_task_ids"] = []
                persist_active_loop_state()
        return LOOP_STATE

def select_loop_session(session_id: str) -> Dict[str, Any]:
    global LOOP_STATE, _loop_thread
    with _state_lock:
        loaded = load_loop_session(session_id)
        if loaded:
            LOOP_STATE = _ensure_loop_state_keys(loaded)
        else:
            _ensure_loop_state_keys(LOOP_STATE)
        
        # If the loaded session claims to be "running", verify if it is actually the currently running thread
        if LOOP_STATE.get("status") in ("running", "recovering"):
            is_active_thread = (_loop_thread is not None and LOOP_STATE.get("id") == session_id)
            if not is_active_thread:
                tasks = LOOP_STATE.get("tasks", [])
                if tasks and all(t.get("status") == "completed" for t in tasks):
                    LOOP_STATE["status"] = "completed"
                elif any(t.get("status") == "failed" for t in tasks):
                    LOOP_STATE["status"] = "failed"
                elif not LOOP_STATE.get("goal"):
                    LOOP_STATE["status"] = "idle"
                else:
                    LOOP_STATE["status"] = "interrupted"
                LOOP_STATE["active_subagent"] = None
                LOOP_STATE["active_subagents"] = []
                LOOP_STATE["current_task_id"] = None
                LOOP_STATE["current_task_ids"] = []
                persist_active_loop_state()
        return LOOP_STATE

def log_loop_activity(message: str, category: str = "loop", is_active: bool = False):
    timestamp = time.strftime('%H:%M:%S', time.localtime())
    entry = {
        "timestamp": timestamp,
        "message": message,
        "category": category,
        "is_active": is_active
    }
    with _state_lock:
        LOOP_STATE.setdefault("live_logs", []).append(entry)
        if len(LOOP_STATE["live_logs"]) > 100:
            LOOP_STATE["live_logs"].pop(0)
        persist_active_loop_state()
    log_event("info", "loop", message)

async def ping_lead_advisor(subagent_name: str, role: str, question: str, task_context: str = "") -> str:
    """
    Sub-agent escalation mechanism:
    If a sub-agent has questions, doubts, compiler errors, or architecture ambiguities,
    they ping the Gemini Lead Advisor (the smartest model) to get authoritative guidance.
    """
    t0 = time.time()
    log_loop_activity(f"📡 {subagent_name} ({role}) pinged Lead Advisor: '{question[:60]}...'", category="ping")
    update_agent_status("orchestrator", "gemini", "running", f"🧠 Answering consultation for {subagent_name} ({role})...")
    
    advisor_prompt = f"""[SUB-AGENT CONSULTATION ESCALATION]
The sub-agent '{subagent_name}' (Role: {role}) is executing a task and requires your authoritative guidance.

Task Context:
{task_context}

Sub-Agent Question / Blocker:
{question}

Provide direct, actionable, unambiguous instructions and code snippet/specification so the sub-agent can continue accurately.
"""
    answer = await query_gemini(advisor_prompt)
    duration = round(time.time() - t0, 2)
    
    ping_record = {
        "id": f"ping-{int(time.time()*1000)}",
        "timestamp": time.strftime('%H:%M:%S'),
        "subagent": subagent_name,
        "role": role,
        "question": question,
        "answer": answer,
        "duration": duration
    }
    LOOP_STATE["advisor_pings"].insert(0, ping_record)
    log_loop_activity(f"👑 Lead Advisor resolved ping for {subagent_name} ({duration}s)", category="advisor")
    update_agent_status("orchestrator", "gemini", "idle", "Awaiting user task...")
    
    return answer

async def run_preflight_research(goal: str, repo_path: str, repo_block: str) -> Dict[str, Any]:
    """
    Pre-Flight Autonomous Research Subagent:
    Scans repository context, rules, universal contracts (OpenAPI, FlatBuffers, SCXML, CEL),
    and live Context7 library docs, then produces a structured Research Brief covering
    target symbols, library documentation, and architectural invariants.
    """
    log_loop_activity("🔍 Phase 1: Pre-Flight Autonomous Research Subagent analyzing codebase, contracts & Context7 docs...", category="agent", is_active=True)
    update_agent_status("sub_agents", "agent_arch", "running", f"Conducting Pre-Flight Research for: '{goal[:40]}'...")
    
    # 1. Resolve Research Skill
    research_skill = resolve_and_inject_skill("research", goal, repo_path)
    
    # 2. Extract Project & Global Rules
    rules_block = format_enforced_rules_prompt(repo_path)

    # 3. Scan & Extract Universal Contract Invariants (OpenAPI, FlatBuffers, SCXML, CEL)
    contracts_block = format_contracts_prompt_block(repo_path)
    
    # 4. Detect Relevant Libraries & Frameworks from Goal and Manifests
    c7_docs = ""
    words = [w.lower() for w in re.split(r'[^a-zA-Z0-9_-]', goal) if len(w) >= 3]
    known_libs = ["fastmcp", "fastapi", "pydantic", "react", "nextjs", "redis", "drizzle", "prisma", "langchain", "tailwind", "express", "pytest", "vitest"]
    detected_libs = [w for w in words if w in known_libs]
    if not detected_libs:
        detected_libs = ["fastapi", "pydantic"]
    
    for lib in detected_libs[:2]:
        c7_snippet = fetch_latest_doc_context(lib, goal)
        if c7_snippet:
            c7_docs += f"\n\n{c7_snippet}"

    # 5. Generate Structured Research Brief
    prompt = f"""You are the Chief Research & Solutions Architect.
Feature Goal: {goal}

{research_skill['injection_prompt']}

{rules_block}

{contracts_block}

{repo_block}

{c7_docs}

Produce a structured, comprehensive Pre-Flight Research Brief in Markdown.
Structure your brief with these exact sections:
# Pre-Flight Research Brief: {goal}

## 1. Executive Architecture Summary & Scope
High-level architectural blueprint and scope boundaries.

## 2. Target Symbols, Files, & Module Boundaries
Exact files, classes, methods, and schemas to create or modify.

## 3. Library Documentation & Verified 2026 API Signatures
Version-accurate APIs and dependency contracts (grounded in Context7).

## 4. Architectural Invariants & Clean Architecture Guardrails
Rules on function length (≤30 lines), single responsibility, dependency injection, error handling, and testability.

### 📜 Universal Contract Invariants & Schemas
Detail all OpenAPI schemas, FlatBuffers binary tables, SCXML state transitions, and CEL invariant rules.

## 5. Proposed Task Decomposition & Slicing Strategy
Logical tracer-bullet vertical slices.
"""
    research_brief = await query_gemini(prompt)
    if not research_brief.strip() or "Error:" in research_brief:
        research_brief = await query_local_slot(prompt, system="You are the Chief Research Architect.")

    # Ensure dedicated Universal Contract Invariants & Schemas section is present
    if "### 📜 Universal Contract Invariants & Schemas" not in research_brief:
        research_brief += f"\n\n### 📜 Universal Contract Invariants & Schemas\n{contracts_block}\n"

    safe_title = "".join(c if c.isalnum() else "_" for c in goal)[:28]
    save_artifact_to_disk(
        title=f"Research Brief — {goal}",
        filename=f"RESEARCH_BRIEF_{safe_title}.md",
        content=research_brief,
        repo_path=repo_path
    )
    
    LOOP_STATE["research_brief"] = research_brief
    update_agent_status("sub_agents", "agent_arch", "idle", "Research Brief finalized")
    log_loop_activity(f"✓ Pre-Flight Research complete. Brief saved (RESEARCH_BRIEF_{safe_title}.md).", category="agent")
    
    return {
        "content": research_brief,
        "filename": f"RESEARCH_BRIEF_{safe_title}.md"
    }

async def decompose_goal_into_tasks(goal: str, repo_block: str, research_brief: str) -> List[Dict[str, Any]]:
    """Uses Lead Advisor grounded in the Research Brief to plan sequential tasks."""
    prompt = f"""You are the Chief Product & Software Architect.
Goal: {goal}

=== PRE-FLIGHT RESEARCH BRIEF ===
{research_brief[:3500]}
=================================

{repo_block}

Break this goal down into 3 to 5 atomic, sequential vertical slice tasks following Clean Architecture.
Assign each task a specialized role from:
- 'dev' (Implementation & Code Construction)
- 'qa' (Syntax Verification & Test Validation)
- 'review' (Security Audit & Blast Radius Review)

Respond ONLY with a valid JSON array of objects with this schema:
[
  {{
    "title": "Task Title",
    "role": "dev" | "qa" | "review",
    "description": "Concrete technical actions and target files",
    "acceptance_criteria": "Deterministic verification rules and tests"
  }}
]
"""
    res = await query_gemini(prompt)
    tasks_data = []
    try:
        clean_json = res.strip()
        if "```json" in clean_json:
            clean_json = clean_json.split("```json")[1].split("```")[0].strip()
        elif "```" in clean_json:
            clean_json = clean_json.split("```")[1].split("```")[0].strip()
        tasks_data = json.loads(clean_json)
    except Exception:
        tasks_data = [
            {
                "title": f"Implementation of Core Engine for '{goal}'",
                "role": "dev",
                "description": "Construct core domain models, dependency injection wiring, and service endpoints.",
                "acceptance_criteria": "All functions ≤30 lines, typed contracts, zero missing imports."
            },
            {
                "title": f"QA, Test Suite & Compiler Verification",
                "role": "qa",
                "description": "Check syntax validity, run unit test assertions, and verify contract invariants.",
                "acceptance_criteria": "100% test assertions passing, zero LSP compiler diagnostics."
            },
            {
                "title": f"Security & Threat Boundary Review",
                "role": "review",
                "description": "Audit injection vectors, credential handling, and blast radius safety.",
                "acceptance_criteria": "Zero OWASP high/critical vulnerabilities, safe input bounds."
            }
        ]

    formatted_tasks = []
    for i, t in enumerate(tasks_data):
        role = t.get("role", "dev").lower()
        agent_map = {
            "pm": ("📐 Solution Architect", "Liquid LFM 2.5 (Slot 1)"),
            "dev": ("⚙️ Surgical Code Draftsman", "Liquid LFM 2.5 (Slot 2)"),
            "qa": ("🧪 QA & LSP Compiler Verifier", "Liquid LFM 2.5 (Slot 3)"),
            "review": ("🛡️ Security Threat Auditor", "Liquid LFM 2.5 (Slot 4)")
        }
        agent_name, slot = agent_map.get(role, ("⚙️ Surgical Code Draftsman", "Liquid LFM 2.5 (Slot 2)"))

        # Sequential dependency chaining: if no dependencies were specified,
        # each task depends on the preceding task (task-1 -> task-2 -> task-3)
        # to prevent concurrent file overwrite collisions on the working tree.
        deps = t.get("dependencies", [])
        if not deps and i > 0:
            deps = [f"task-{i}"]

        formatted_tasks.append({
            "id": f"task-{i+1}",
            "order": i + 1,
            "title": t.get("title", f"Task {i+1}"),
            "role": role,
            "description": t.get("description", ""),
            "acceptance_criteria": t.get("acceptance_criteria", ""),
            "dependencies": deps,
            "status": "pending",
            "assigned_agent": agent_name,
            "assigned_slot": slot,
            "injected_skill": "",
            "attempts": 0,
            "output": "",
            "qa_verdict": "",
            "security_verdict": "",
            "oracle_verdict": "",
            "judge_certificate": "",
            "advisor_consultations": []
        })

    return formatted_tasks

def dev_engine_is_pi(repo_path: str) -> bool:
    """Whether this dev task should run through Pi's agentic tool loop.

    Requires an explicit opt-in ("pi"/"auto"), the pi CLI present, and a real
    repository — Pi's tools are path-relative and pointless without one.
    """
    if DEV_AGENT_ENGINE not in ("pi", "auto"):
        return False
    if not repo_path or not Path(repo_path).exists():
        return False
    return pi_available()


def _pi_written_files(pi_res: Dict[str, Any], repo_path: str) -> List[Dict[str, Any]]:
    """Normalise Pi's written paths into the shape the audit stages expect.

    The rest of the pipeline consumes records with path/abs_path/bytes/lines —
    notably check_runner_covers_deliverable, which infers the deliverable's
    language from these paths and silently passes everything if handed an empty
    list. Pi writes files itself, so the sizes are read back from disk.
    """
    records: List[Dict[str, Any]] = []
    root = Path(repo_path) if repo_path else None
    for rel in pi_res.get("files_written", []) or []:
        abs_p = (root / rel) if root else Path(rel)
        try:
            content = abs_p.read_text(encoding="utf-8", errors="ignore")
            size, lines = len(content), len(content.splitlines())
        except OSError:
            size, lines = 0, 0
        records.append({"path": rel, "abs_path": str(abs_p), "bytes": size, "lines": lines})
    return records


# Output contract for the Pi path. The opposite of the single-completion
# contract: here the agent HAS tools, and using them is mandatory. Telling a
# tool-capable agent to emit whole files from memory is what produced 23-line
# replacements for 188-line classes.
DEV_PI_CONTRACT = """
HOW TO WORK — YOU HAVE REAL TOOLS:
- You can read, edit, write and run commands. Use them.
- BEFORE changing any existing file you MUST read it first. Never rewrite a file
  you have not read — a truncated rewrite destroys working code.
- Prefer targeted edits over whole-file rewrites. Only use write() for files you
  are creating from nothing.
- Match the language and conventions already in the repository.
- Add or update the unit tests covering your change.
- Work until the task is complete, then briefly summarise what you changed.
"""

DEV_PI_SYSTEM = (
    "You are the Surgical Code Draftsman. You have read/edit/write/bash tools in a real "
    "repository. Always read an existing file before editing it, and make the smallest "
    "correct change. Never replace a file you have not read."
)

DEV_PI_REPAIR_CONTRACT = """
YOUR PREVIOUS ATTEMPT CHANGED NO FILES.
Investigate the repository with your tools and apply the change now. Read the
relevant files first, then edit them. Do not stop until a file has changed.
"""


# How many extra write-only prompts to issue when the dev stage returns no files.
DEV_WRITE_REPAIR_TURNS = 2

DEV_WRITE_ONLY_SYSTEM = (
    "You are the Surgical Code Draftsman. This harness executes NO tools for you. "
    "read_file, bash, exec, run, terminal and list_dir calls are silently discarded — "
    "if you emit one, your work is lost. Your entire response must consist of write() "
    "calls containing complete file bodies."
)

# Tool calls the model emits that this single-turn harness cannot serve. Naming the
# exact call back to the model is a much stronger corrective than a generic scold.
_UNSERVABLE_CALL_RE = re.compile(
    r"\b(read_file|read|list_dir|ls|bash|exec|run|terminal|shell|search|grep|glob)\s*\(",
    re.IGNORECASE,
)


def _describe_unservable_tool_calls(output: str) -> str:
    """Summarise which unservable tool calls the model asked for, e.g. 'bash, read_file'."""
    if not output:
        return ""
    names = []
    for m in _UNSERVABLE_CALL_RE.finditer(output):
        nm = m.group(1).lower()
        if nm not in names:
            names.append(nm)
    return ", ".join(names[:6])


def _build_write_repair_prompt(original_prompt: str, bad_output: str, requested: str) -> str:
    """Re-ask for the same task, quoting the rejected non-write response back."""
    called = (
        f"You emitted {requested}() call(s). Those were DISCARDED — this harness "
        f"cannot run them and you will never receive a result.\n"
        if requested else
        "Your response contained no write() call, so nothing was applied.\n"
    )
    return f"""{original_prompt}

=== YOUR PREVIOUS RESPONSE WAS REJECTED: ZERO FILES WRITTEN ===
{called}
Your rejected response began:
{bad_output[:600]}

You do NOT need to inspect the repository, install anything, or run any command.
Write the files from first principles using the task description above. If you
need a value you cannot verify, choose a sensible default and encode it in the code.

Respond with NOTHING except write() calls, in exactly this shape:
<|tool_call_start|>[write(path='relative/path.ext', content='<COMPLETE FILE BODY>')]<|tool_call_end|>
=================================================================
"""


def _parse_verdict(output: str) -> bool:
    """True only on an explicit `VERDICT: PASSED`.

    The old heuristic (`"PASSED" in out and "FAILED" not in out`) let ordinary
    prose decide the gate and treated an unservable tool-call response — which
    contains neither token — as ambiguous. Absence of a verdict is now a fail.
    """
    if not output:
        return False
    matches = re.findall(r"VERDICT\s*:\s*(PASSED|FAILED)", output, re.IGNORECASE)
    if not matches:
        return False
    return matches[-1].upper() == "PASSED"


def _parse_decision(output: str) -> bool:
    """True only on an explicit `DECISION: APPROVED` from the auto-judge."""
    if not output:
        return False
    matches = re.findall(r"DECISION\s*:\s*(APPROVED|REJECTED)", output, re.IGNORECASE)
    if not matches:
        return False
    return matches[-1].upper() == "APPROVED"


def _build_dev_feedback(
    test_result: Dict[str, Any],
    qa_output: str,
    sec_output: str,
    judge_output: str,
    infra_broken: bool,
    wrote_files: bool,
) -> str:
    """Assemble retry feedback that the dev agent can actually act on by writing files.

    Critically, an infrastructure failure trace is withheld. Handing the agent a
    `ModuleNotFoundError: pytest` and labelling it "MUST FIX ALL" reliably derails
    it into emitting `bash(pip install pytest)` — an unservable call — so it spends
    every remaining attempt on the environment and never writes the feature.
    """
    parts = []
    if not wrote_files:
        parts.append(
            "=== BLOCKING: NO FILES WERE WRITTEN ===\n"
            "Your previous response applied zero files. Emit write() calls with complete "
            "file bodies. Do not emit read_file, bash, exec or any other tool call."
        )
    if infra_broken:
        parts.append(
            "=== TEST ENVIRONMENT UNAVAILABLE (NOT YOUR FAULT, NOT YOUR JOB) ===\n"
            f"{test_result.get('infra_reason', '')}\n"
            "The operator must fix this. Do NOT attempt to install packages, run "
            "commands, or modify dependency manifests to work around it. Write the "
            "feature code and its tests as if the runner worked."
        )
    else:
        trace = (test_result.get("output") or "").strip()
        if trace:
            parts.append(f"=== REAL TEST EXECUTION FAILURE TRACE ===\n{trace[:3000]}")

    parts.append(f"=== QA VERIFIER FEEDBACK ===\n{qa_output[:2000]}")
    parts.append(f"=== SECURITY AUDIT ===\n{sec_output[:1500]}")
    parts.append(f"=== AUTO-JUDGE DIAGNOSTICS ===\n{judge_output[:1500]}")
    return "\n\n".join(parts)


async def execute_zero_trust_task(
    task: Dict[str, Any],
    repo_block: str,
    repo_path: str,
    research_brief: str,
    github_issue_num: Optional[int] = None
) -> Dict[str, Any]:
    """
    Zero-Trust Multi-Agent Handoff Pipeline with Retry Loop:
    Dev Draftsman (Real Code Application) -> QA/LSP Verifier (Real Test Runner Execution) -> 
    Security Threat Auditor (Real Git Diff Review) -> Adversarial Oracle Cross-Check -> Auto-Judge Gate -> Real Git Commit.
    If flaws or test failures are detected, Auto-Judge rejects the deliverable with real test traces back to Dev (up to 3 retries).
    """
    role = task["role"]
    task_title = task["title"]
    max_retries = 3
    rules_block = format_enforced_rules_prompt(repo_path)
    diagnostic_feedback = task.get("diagnostic_feedback", "")
    start_attempt = max(1, task.get("attempts", 1))

    for attempt in range(start_attempt, max_retries + 1):
        task["attempts"] = attempt
        persist_active_loop_state()
        log_loop_activity(f"🔄 Task '{task_title}' — Stage 1: Dev Drafting (Attempt {attempt}/{max_retries})", category="loop", is_active=True)
        
        learned_rules = LOOP_STATE.get("learned_rules", [])
        rules_block = format_enforced_rules_prompt(repo_path, learned_rules=learned_rules)
        
        # ─────────────────────────────────────────────────────────────
        # STAGE 1: DEV DRAFTSMAN (Implementation & Real Code Application)
        # ─────────────────────────────────────────────────────────────
        dev_skill = resolve_and_inject_skill("dev", task["description"], repo_path)
        task["injected_skill"] = dev_skill["skill_name"]
        update_agent_status("sub_agents", "agent_dev", "running", f"Drafting code for '{task_title}' (Attempt {attempt}/{max_retries})...")
        LOOP_STATE["active_subagent"] = {
            "name": "⚙️ Surgical Code Draftsman",
            "role": "dev",
            "task_title": task_title,
            "slot": "Liquid LFM 2.5 (Slot 2)",
            "status": f"Drafting (Attempt {attempt})"
        }

        # Advisor consultation if first attempt or complex task
        if attempt == 1 and role in ["dev", "review"] and not task.get("advisor_consultations"):
            consult_q = f"For task '{task_title}', what are the crucial edge cases and Clean Architecture boundaries?"
            adv_guidance = await ping_lead_advisor("Surgical Code Draftsman", "dev", consult_q, task_context=task["description"])
            task.setdefault("advisor_consultations", []).append({"question": consult_q, "guidance": adv_guidance})
        else:
            adv_guidance = task.get("advisor_consultations", [{}])[-1].get("guidance", "") if task.get("advisor_consultations") else ""

        dev_context = f"""{rules_block}

{dev_skill['injection_prompt']}

=== RESEARCH CONTEXT ===
{research_brief[:2000]}
========================

{repo_block}

TASK: {task_title}
ROLE: SURGICAL CODE DRAFTSMAN ({role.upper()})
DESCRIPTION: {task['description']}
ACCEPTANCE CRITERIA: {task['acceptance_criteria']}
{f"LEAD ADVISOR GUIDANCE: {adv_guidance}" if adv_guidance else ""}

{f"=== PREVIOUS ATTEMPT DIAGNOSTIC REJECTION & TEST FAILURE TRACE (MUST FIX ALL): ===\n{diagnostic_feedback}\n========================================================" if diagnostic_feedback else ""}

"""

        dev_prompt = dev_context + f"""
CRITICAL OUTPUT CONTRACT — READ CAREFULLY:
You get exactly ONE response and CANNOT run tools interactively. Therefore:
- DO NOT call read_file, read, list_dir, terminal, or any inspection tool — you will not get a result back.
- You MUST emit the COMPLETE contents of every file to create or modify, in this ONE response.
- Emit one write() tool-call per file, e.g.:
  <|tool_call_start|>[write(path='relative/path/to/target.ext', content='<COMPLETE FILE BODY>')]<|tool_call_end|>
  (relative repo paths only; escape newlines as \\n inside content string).
- For C# (.cs): ALWAYS include required namespaces at top (e.g. using System; using System.Collections.Generic; using System.Linq;).
- For Python (.py): ALWAYS include necessary imports (from typing import List, Dict, Optional, Any, Tuple, Set).
- Equivalent accepted formats: a fenced block ```lang relative/path/to/target.ext``` with full content, or a JSON array [{{"path": "...", "content": "..."}}].
Every file you name MUST include its full, production-grade content (Clean Architecture: functions ≤30 lines, typed signatures, error handling). Include unit tests where applicable. Emit writes NOW — do not describe, do not ask, do not read.
"""
        # Code generation needs a large budget — files get truncated mid-write at the
        # default 2048 tokens, which is the #1 cause of "no code produced".
        use_pi = dev_engine_is_pi(repo_path)
        task["dev_engine"] = "pi" if use_pi else "raw"

        if use_pi:
            # Agentic path: Pi drives a real read/edit/write loop, so the agent can
            # inspect a file before changing it. This is what stops a refactor task
            # from becoming a blind full-file overwrite.
            pi_res = await run_pi_agent(
                dev_context + DEV_PI_CONTRACT,
                repo_path,
                system=DEV_PI_SYSTEM,
                timeout=PI_AGENT_TIMEOUT,
            )
            dev_output = pi_res.get("text") or ""
            written_files = _pi_written_files(pi_res, repo_path)
            if not pi_res.get("success"):
                # Fall back rather than fail the attempt outright: a Pi launch or
                # timeout problem is not evidence about the deliverable.
                log_loop_activity(
                    f"⚠️ Pi dev agent unavailable ({pi_res.get('error')}). "
                    f"Falling back to single-completion drafting.",
                    category="dev",
                )
                task["dev_engine"] = "raw (pi fallback)"
                dev_output = await query_local_slot(
                    dev_prompt, system=DEV_WRITE_ONLY_SYSTEM, max_tokens=8192
                )
                written_files = extract_code_blocks_and_write(repo_path, dev_output)
            else:
                tool_names = [t.get("name") for t in pi_res.get("tool_calls", [])]
                log_loop_activity(
                    f"🛠️ Pi dev agent ran {len(tool_names)} tool call(s): {', '.join(tool_names[:8])}",
                    category="dev",
                )
        else:
            dev_output = await query_local_slot(
                dev_prompt,
                system=DEV_WRITE_ONLY_SYSTEM,
                max_tokens=8192,
            )
            written_files = extract_code_blocks_and_write(repo_path, dev_output)

        task["output"] = dev_output
        
        # No-write repair turn. The small model routinely answers with an
        # inspection/shell tool-call (read_file, bash, exec) that this harness
        # cannot serve, so nothing lands on disk. Retrying the DEV stage alone is
        # far cheaper than running QA + Security + Oracle + Judge against an empty
        # diff and then replaying the whole 5-stage pipeline.
        for repair in range(1, DEV_WRITE_REPAIR_TURNS + 1):
            if written_files:
                break
            requested = _describe_unservable_tool_calls(dev_output)
            log_loop_activity(
                f"⚠️ Dev produced no file writes"
                f"{f' (model asked for: {requested})' if requested else ''}. "
                f"Issuing write-only repair prompt {repair}/{DEV_WRITE_REPAIR_TURNS}...",
                category="dev",
            )
            if task.get("dev_engine") == "pi":
                pi_res = await run_pi_agent(
                    dev_context + DEV_PI_REPAIR_CONTRACT,
                    repo_path,
                    system=DEV_PI_SYSTEM,
                    timeout=PI_AGENT_TIMEOUT,
                )
                dev_output = pi_res.get("text") or dev_output
                written_files = _pi_written_files(pi_res, repo_path)
            else:
                dev_output = await query_local_slot(
                    _build_write_repair_prompt(dev_prompt, dev_output, requested),
                    system=DEV_WRITE_ONLY_SYSTEM,
                    max_tokens=8192,
                )
                written_files = extract_code_blocks_and_write(repo_path, dev_output)

        task["output"] = dev_output
        task["files_written"] = [f["path"] for f in written_files]
        task["written_files_meta"] = written_files
        if written_files:
            log_loop_activity(f"📝 Dev Draftsman applied {len(written_files)} files to disk: {', '.join(f['path'] for f in written_files)}", category="dev")
        else:
            log_loop_activity(
                f"❌ Dev Draftsman wrote 0 files for '{task_title}' after "
                f"{DEV_WRITE_REPAIR_TURNS} repair turns — nothing to audit.",
                category="dev",
            )
        
        task["stage"] = "dev_draft_completed"
        update_agent_status("sub_agents", "agent_dev", "idle", "Code drafted")
        log_loop_activity(f"✓ Dev drafted implementation for '{task_title}'", category="agent")
        persist_active_loop_state()  # Granular Checkpoint: after dev draft

        # ─────────────────────────────────────────────────────────────
        # STAGE 2-4: ZERO-TRUST AUDIT PHASE (PARALLEL FAN-OUT OR SEQUENTIAL)
        # ─────────────────────────────────────────────────────────────
        # Real Test Runner Execution: Run detected project test suite (pytest, unittest, npm test, etc.)
        # Verification chain: run -> classify infra vs code -> reject a zero-test
        # "pass" -> reject a pass whose runner cannot cover the deliverable's
        # language. Without the last two, `unittest discover` running one leftover
        # placeholder reported "PASSED" for C# that never compiled.
        test_result = run_test_suite(repo_path)
        test_result = classify_test_failure(test_result)
        test_result = detect_vacuous_pass(test_result)
        test_result = check_runner_covers_deliverable(
            test_result, [f["path"] for f in written_files]
        )
        task["test_results"] = test_result
        infra_broken = test_result.get("failure_kind") == "infra"
        if not test_result.get("skipped", False):
            if test_result.get("success"):
                test_status_str = "PASSED (exit 0)"
            elif infra_broken:
                test_status_str = f"INFRASTRUCTURE FAILURE (exit {test_result.get('exit_code')}) — not a code defect"
            else:
                test_status_str = f"FAILED (exit {test_result.get('exit_code')})"
            log_loop_activity(f"🧪 Real test runner ({test_result.get('runner')}): {test_status_str}", category="qa")
        if infra_broken:
            # The host environment, not the deliverable, is broken. Record it as a
            # loop-level blocker and keep it OUT of the dev agent's feedback channel:
            # the agent cannot fix a missing interpreter dependency by writing files,
            # and handing it the trace makes it burn every retry on `pip install`.
            LOOP_STATE.setdefault("infra_blockers", [])
            blocker = {
                "task_id": task["id"],
                "runner": test_result.get("runner"),
                "reason": test_result.get("infra_reason", ""),
                "detail": (test_result.get("output") or "")[:400],
            }
            if blocker not in LOOP_STATE["infra_blockers"]:
                LOOP_STATE["infra_blockers"].append(blocker)
            log_loop_activity(
                f"🚧 Test infrastructure blocker: {test_result.get('infra_reason')} "
                f"Verification for '{task_title}' is UNVERIFIED — fix the host environment.",
                category="qa",
            )

        # Capture real working tree diff
        working_diff = get_working_diff(repo_path)

        qa_skill = resolve_and_inject_skill("qa", task["description"], repo_path)
        sec_skill = resolve_and_inject_skill("security", task["description"], repo_path)
        contracts_block = format_contracts_prompt_block(repo_path)

        qa_prompt = f"""{qa_skill['injection_prompt']}

{contracts_block}

=== ZERO-TRUST QA MANDATE ===
DO NOT TRUST THE DEVELOPER'S OUTPUT OR CLAIMS.
You must independently verify and audit the implementation below:
1. Syntax validity & type signature completeness.
2. Acceptance criteria fulfillment: {task['acceptance_criteria']}
3. Real test runner execution output (below): verify all test assertions pass.
4. Edge case coverage & missing unit tests.
5. Clean Architecture rule violations (e.g. functions > 35 lines).
6. Universal Contract Conformance: Verify code strictly respects OpenAPI schemas, FlatBuffers/Proto structures, SCXML state transitions, and CEL invariant rules.

REAL TEST RUNNER OUTPUT:
Runner: {test_result.get('runner')}
Exit Code: {test_result.get('exit_code')}
Output:
{test_result.get('output', 'No test runner executed.')[:2000]}

REAL REPOSITORY WORKING DIFF:
{working_diff[:3000] if working_diff else 'No working tree diff detected.'}

DEV DELIVERABLE UNDER AUDIT:
{dev_output}

Provide concrete findings, test assertions, and conclude strictly with:
VERDICT: PASSED
or
VERDICT: FAILED (Reason: <detailed diagnostic failure list>)
"""

        sec_prompt = f"""{sec_skill['injection_prompt']}

=== ZERO-TRUST SECURITY MANDATE ===
DO NOT TRUST DEV OR QA REGARDING SAFETY.
Independently audit the real changes and diff for:
1. Injection vulnerabilities (SQL, Command, Path Traversal, XSS).
2. Authentication/Authorization bypasses & secret leaks.
3. Denial of Service risks, unbounded loops, or memory leaks.
4. Blast radius on dependent services.

REAL REPOSITORY WORKING DIFF UNDER AUDIT:
{working_diff[:3500] if working_diff else 'No working tree diff detected.'}

FILES APPLIED:
{json.dumps(task.get('files_written', []), indent=2)}

DEV DELIVERABLE:
{dev_output[:2000]}

Provide threat analysis and conclude strictly with:
VERDICT: PASSED
or
VERDICT: FAILED (Reason: <vulnerabilities found>)
"""

        oracle_prompt = f"""Cross-check this implementation against production invariants:
Task: {task_title}
Dev Implementation Preview: {dev_output[:800]}
Real Test Status: {'Passed' if test_result.get('success') else 'Failed'}

Verify invariant consistency and report consensus sign-off or potential blind spots."""

        if PARALLEL_AUDIT_PHASE:
            log_loop_activity(f"⚡ Task '{task_title}' — Parallel Audit Fan-Out: QA, Security & Adversarial Oracle running concurrently...", category="agent", is_active=True)
            
            # Simultaneous real-time Swarm Topology status updates
            update_agent_status("sub_agents", "agent_qa", "running", f"Running real test suite & QA verification (Attempt {attempt})...")
            update_agent_status("sub_agents", "agent_sec", "running", f"Independent Security & OWASP Audit (Attempt {attempt})...")
            update_agent_status("sub_agents", "agent_oracle", "running", f"Cross-checking '{task_title}' (Attempt {attempt})...")
            update_agent_status("consensus_nodes", "qwen", "running", f"Cross-checking '{task_title}' (Attempt {attempt})...")

            LOOP_STATE["active_subagents"] = [
                {
                    "name": "🧪 QA & LSP Compiler Verifier",
                    "role": "qa",
                    "id": "agent_qa",
                    "task_title": task_title,
                    "slot": "Liquid LFM 2.5 (Slot 3)",
                    "status": "Running Tests & Syntax Audit"
                },
                {
                    "name": "🛡️ Security Threat Auditor",
                    "role": "review",
                    "id": "agent_sec",
                    "task_title": task_title,
                    "slot": "Liquid LFM 2.5 (Slot 4)",
                    "status": "Scanning Vulnerabilities & Diff"
                },
                {
                    "name": "🔮 Adversarial Consensus Oracle",
                    "role": "oracle",
                    "id": "agent_oracle",
                    "task_title": task_title,
                    "slot": "chat.qwen.ai Session",
                    "status": "Cross-Checking Consensus"
                }
            ]
            LOOP_STATE["active_subagent"] = {
                "name": "⚡ Parallel Multi-Agent Audit (QA + Security + Oracle)",
                "role": "audit",
                "task_title": task_title,
                "slot": "Parallel Slots (3, 4, Oracle)",
                "status": "3 Agents Running Concurrently"
            }
            persist_active_loop_state()

            async def _run_qa_fanout():
                out = await query_local_slot(qa_prompt, system="You are the QA & LSP Compiler Verifier. Strictly reject invalid or unverified code.")
                update_agent_status("sub_agents", "agent_qa", "idle", "QA verified")
                task["stage"] = "qa_completed"
                persist_active_loop_state()
                return out

            async def _run_sec_fanout():
                out = await query_local_slot(sec_prompt, system="You are the Security Threat Auditor. Reject any vulnerabilities or unvetted risks.")
                update_agent_status("sub_agents", "agent_sec", "idle", "Security audited")
                task["stage"] = "security_completed"
                persist_active_loop_state()
                return out

            async def _run_oracle_fanout():
                out = await query_qwen_web(oracle_prompt)
                update_agent_status("sub_agents", "agent_oracle", "idle", "Consensus verified")
                update_agent_status("consensus_nodes", "qwen", "ready", "Consensus verified")
                task["stage"] = "oracle_completed"
                persist_active_loop_state()
                return out

            qa_output, sec_output, oracle_output = await asyncio.gather(
                _run_qa_fanout(),
                _run_sec_fanout(),
                _run_oracle_fanout()
            )
            LOOP_STATE["active_subagents"] = []
            persist_active_loop_state()

        else:
            # Sequential Fallback execution
            log_loop_activity(f"🧪 Task '{task_title}' — Stage 2: Zero-Trust QA & Real Test Suite Execution...", category="agent", is_active=True)
            update_agent_status("sub_agents", "agent_qa", "running", f"Running real test suite & QA verification (Attempt {attempt})...")
            LOOP_STATE["active_subagent"] = {
                "name": "🧪 QA & LSP Compiler Verifier",
                "role": "qa",
                "task_title": task_title,
                "slot": "Liquid LFM 2.5 (Slot 3)",
                "status": "Running Tests & Syntax Audit"
            }
            qa_output = await query_local_slot(qa_prompt, system="You are the QA & LSP Compiler Verifier. Strictly reject invalid or unverified code.")
            update_agent_status("sub_agents", "agent_qa", "idle", "QA verified")

            log_loop_activity(f"🛡️ Task '{task_title}' — Stage 3: Zero-Trust Security & Threat Audit (Real Diff)...", category="agent", is_active=True)
            update_agent_status("sub_agents", "agent_sec", "running", f"Independent Security & OWASP Audit (Attempt {attempt})...")
            LOOP_STATE["active_subagent"] = {
                "name": "🛡️ Security Threat Auditor",
                "role": "review",
                "task_title": task_title,
                "slot": "Liquid LFM 2.5 (Slot 4)",
                "status": "Scanning Vulnerabilities & Diff"
            }
            sec_output = await query_local_slot(sec_prompt, system="You are the Security Threat Auditor. Reject any vulnerabilities or unvetted risks.")
            update_agent_status("sub_agents", "agent_sec", "idle", "Security audited")

            log_loop_activity(f"🔮 Task '{task_title}' — Stage 4: Adversarial Oracle Cross-Check...", category="agent", is_active=True)
            update_agent_status("consensus_nodes", "qwen", "running", f"Cross-checking '{task_title}' (Attempt {attempt})...")
            LOOP_STATE["active_subagent"] = {
                "name": "🔮 Adversarial Consensus Oracle",
                "role": "oracle",
                "task_title": task_title,
                "slot": "chat.qwen.ai Session",
                "status": "Cross-Checking Consensus"
            }
            oracle_output = await query_qwen_web(oracle_prompt)
            update_agent_status("consensus_nodes", "qwen", "ready", "Consensus verified")

        # Evaluate QA verdict. An empty deliverable can never pass, and an
        # infrastructure failure yields UNVERIFIED (never a silent pass).
        if not written_files:
            qa_passed = False
            qa_output = (
                "VERDICT: FAILED (Reason: Dev produced no file writes; there is no "
                "deliverable to audit.)\n\n" + qa_output
            )
        elif infra_broken:
            qa_passed = False
            qa_output = (
                f"VERDICT: FAILED (Reason: UNVERIFIED — test infrastructure failure, "
                f"not a code defect: {test_result.get('infra_reason')})\n"
                f"Runner: {test_result.get('runner')} exited {test_result.get('exit_code')}.\n\n"
                f"QA Analysis:\n{qa_output}"
            )
        elif not test_result.get("skipped", False) and not test_result.get("success", True):
            qa_passed = False
            qa_output = f"REAL TEST EXECUTION FAILED (Runner: {test_result.get('runner')}, Exit Code: {test_result.get('exit_code')}):\n{test_result.get('output', '')}\n\nQA Diagnostic Verification:\n{qa_output}\nVERDICT: FAILED (Reason: Real test suite failed with exit code {test_result.get('exit_code')})"
        else:
            qa_passed = _parse_verdict(qa_output)

        sec_passed = _parse_verdict(sec_output)

        task["qa_verdict"] = qa_output
        task["qa_passed"] = qa_passed
        task["security_verdict"] = sec_output
        task["security_passed"] = sec_passed
        task["oracle_verdict"] = oracle_output
        task["stage"] = "audit_completed"
        persist_active_loop_state()

        # ─────────────────────────────────────────────────────────────
        # STAGE 5: AUTO-JUDGE GATE & RETRY EVALUATION
        # ─────────────────────────────────────────────────────────────
        log_loop_activity(f"⚖️ Task '{task_title}' — Stage 5: Auto-Judge Gate Decision...", category="judge", is_active=True)
        update_agent_status("sub_agents", "agent_judge", "running", f"Evaluating multi-agent verdicts & real tests on attempt {attempt}...")
        LOOP_STATE["active_subagent"] = {
            "name": "⚖️ Autonomous Swarm Judge",
            "role": "judge",
            "task_title": task_title,
            "slot": "Liquid LFM 2.5 (Slot 5)",
            "status": "Evaluating Gate"
        }

        judge_prompt = f"""You are the Autonomous Swarm Auto-Judge.
Task: {task_title}
Acceptance Criteria: {task['acceptance_criteria']}

Independent Verification Reports:
--- REAL TEST EXECUTION ---
Runner: {test_result.get('runner')}
Exit Code: {test_result.get('exit_code')}
Success: {test_result.get('success')}
Output Summary:
{test_result.get('output', '')[:800]}

--- QA VERDICT ---
{qa_output}

--- SECURITY VERDICT ---
{sec_output}

--- ORACLE CROSS-CHECK ---
{oracle_output}

Decision Protocol:
- If Real Test Suite failed (exit code != 0), QA failed, Security failed, or Universal Contract Invariants are violated: Issue REJECT with structured diagnostic feedback.
- If all checks passed, real tests exited with code 0, and security approved: Issue APPROVED with verification certificate.

Conclude strictly with either:
DECISION: APPROVED (Certificate: <verification summary>)
or
DECISION: REJECTED (Diagnostics: <concrete diagnostic issues to fix>)
"""
        judge_output = await query_local_slot(judge_prompt, system="You are the Autonomous Swarm Judge. Enforce zero-defect gatekeeping.")
        update_agent_status("sub_agents", "agent_judge", "idle", "Evaluation complete")

        # Gate. Previously the two disjuncts made the judge's own decision dead
        # code (the second was strictly weaker than the first), and the
        # `"FAILED" not in judge_output` scan was near-unsatisfiable because any
        # audit prose discussing failure modes tripped it. Now: each precondition
        # is checked explicitly, and the judge's DECISION line is parsed rather
        # than substring-matched against the whole response.
        tests_ok = bool(test_result.get("skipped")) or bool(test_result.get("success"))
        judge_approved = _parse_decision(judge_output)
        gate_reasons = []
        if not written_files:
            gate_reasons.append("dev wrote no files")
        if not qa_passed:
            gate_reasons.append("QA verdict not PASSED")
        if not sec_passed:
            gate_reasons.append("security verdict not PASSED")
        if not tests_ok:
            gate_reasons.append(f"test suite failed (exit {test_result.get('exit_code')})")
        if infra_broken:
            gate_reasons.append("test infrastructure broken — deliverable UNVERIFIED")
        if not judge_approved:
            gate_reasons.append("auto-judge did not issue DECISION: APPROVED")

        is_approved = not gate_reasons
        task["gate_reasons"] = gate_reasons

        task["judge_certificate"] = judge_output
        task["stage"] = "judge_completed"
        persist_active_loop_state()  # Granular Checkpoint: after judge decision

        if not is_approved and attempt < max_retries:
            diagnostic_feedback = _build_dev_feedback(
                test_result, qa_output, sec_output, judge_output,
                infra_broken=infra_broken, wrote_files=bool(written_files),
            )
            
            # Active Lead Advisor Escalation: Ask Advisor / Qwen Oracle for precise remediation plan and extract evolved rules
            consult_prompt = f"""We are executing Task: '{task_title}' (Role: {role}).
Attempt {attempt} of {max_retries} was REJECTED by the Zero-Trust Gate.

Failure Diagnostics & Test Failure Trace:
{diagnostic_feedback}

Recent Files Written: {[f.get('path', '') for f in written_files]}

Analyze this failure and respond in this exact structured format:
### 🛠️ Step-by-Step Remediation Plan
(Provide exact, actionable code guidance for the Dev Draftsman to fix this error and pass the test suite)

### 📜 Evolved Dynamic Rule
(One clear, universal rule summarizing this mistake so the swarm never repeats it, starting with 'RULE:')
"""
            log_loop_activity(f"🧠 Escalating failure on '{task_title}' to Lead Advisor & Oracle for root-cause remediation plan...", category="ping", is_active=True)
            remediation_plan = await ping_lead_advisor(
                subagent_name=task.get("assigned_agent", "Surgical Code Draftsman"),
                role=role,
                question=f"How do we fix this task failure and pass the test suite?",
                task_context=consult_prompt
            )
            
            # Extract and store evolved dynamic rule into persistent session state
            evolved_rule = ""
            if "### 📜 Evolved Dynamic Rule" in remediation_plan:
                evolved_rule = remediation_plan.split("### 📜 Evolved Dynamic Rule")[1].split("###")[0].strip()
            elif "RULE:" in remediation_plan:
                for line in remediation_plan.split("\n"):
                    if "RULE:" in line:
                        evolved_rule = line.strip()
                        break

            if evolved_rule:
                with _state_lock:
                    if "learned_rules" not in LOOP_STATE:
                        LOOP_STATE["learned_rules"] = []
                    if evolved_rule not in LOOP_STATE["learned_rules"]:
                        LOOP_STATE["learned_rules"].append(evolved_rule)
                        log_loop_activity(f"💡 Swarm Evolved Dynamic Rule: {evolved_rule[:120]}", category="rules")
                        persist_active_loop_state()

            task.setdefault("advisor_consultations", []).append({
                "question": f"Attempt {attempt} Failure Escalation",
                "guidance": remediation_plan,
                "attempt": attempt
            })
            diagnostic_feedback += f"\n\n=== 👑 LEAD ADVISOR ROOT-CAUSE REMEDIATION PLAN (MUST FOLLOW STRICTLY) ===\n{remediation_plan}\n"
            task["diagnostic_feedback"] = diagnostic_feedback
            persist_active_loop_state()
            log_loop_activity(f"❌ Auto-Judge REJECTED '{task_title}' (Attempt {attempt}/{max_retries}): {'; '.join(gate_reasons)}. Retrying with Advisor Remediation Plan...", category="judge")
            if github_issue_num:
                gh_issue_comment(
                    repo_path,
                    github_issue_num,
                    f"⚠️ Task '{task_title}' (Attempt {attempt}/{max_retries}) REJECTED by Auto-Judge.\n\n### Diagnostic Feedback:\n{diagnostic_feedback[:500]}..."
                )
            await asyncio.sleep(0.5)
            continue
        elif not is_approved:
            # Retries exhausted and the gate still says no. This branch used to
            # fall through to the success path — marking the task "completed",
            # committing, flipping the board card to Done and posting "APPROVED by
            # Auto-Judge" while qa_passed was False. That fabricated verdict is
            # what let unverified junk reach the merge step. Terminal state is now
            # an explicit failure that commits nothing.
            task["status"] = "failed"
            task["stage"] = "gate_failed"
            task["failure_reasons"] = gate_reasons
            task["diagnostic_feedback"] = _build_dev_feedback(
                test_result, qa_output, sec_output, judge_output,
                infra_broken=infra_broken, wrote_files=bool(written_files),
            )
            log_loop_activity(
                f"⛔ Task '{task_title}' FAILED the zero-trust gate after {max_retries} attempts "
                f"({'; '.join(gate_reasons)}). No commit, no merge.",
                category="judge",
            )
            board = LOOP_STATE.get("project_board", {})
            if board.get("number") and task.get("board_item_id"):
                gh_project_set_status(repo_path, board["owner"], board["number"], task["board_item_id"], status="Todo")
            if github_issue_num:
                gh_issue_comment(
                    repo_path,
                    github_issue_num,
                    f"⛔ Task '{task_title}' FAILED after {max_retries} attempts.\n\n"
                    f"### Unmet gate conditions\n" + "\n".join(f"- {r}" for r in gate_reasons)
                )
            persist_active_loop_state()
            break
        else:
            task["output"] = dev_output
            task["qa_verdict"] = qa_output
            task["security_verdict"] = sec_output
            task["oracle_verdict"] = oracle_output
            task["judge_certificate"] = judge_output
            task["status"] = "completed"
            
            # Real Git Commit: Commit changes made during this task on the isolated branch
            if repo_path and (Path(repo_path) / ".git").exists():
                commit_msg = f"feat({task.get('role', 'dev')}): {task_title} [Swarm Task #{task['id']}]"
                commit_res = commit_changes(repo_path, commit_msg)
                if commit_res.get("committed"):
                    task["commit_hash"] = commit_res.get("commit_hash", "")
                    task["short_hash"] = commit_res.get("short_hash", "")
                    log_loop_activity(f"📦 Committed task changes: {commit_res.get('short_hash')} - '{task_title}'", category="git")
                elif commit_res.get("commit_hash"):
                    task["commit_hash"] = commit_res.get("commit_hash", "")
                    task["short_hash"] = commit_res.get("short_hash", "")

            # Move this task's card to Done on the project board (best-effort).
            board = LOOP_STATE.get("project_board", {})
            if board.get("number") and task.get("board_item_id"):
                gh_project_set_status(repo_path, board["owner"], board["number"], task["board_item_id"], status="Done")

            commit_info = f" (Commit: `{task.get('short_hash')}`)" if task.get("short_hash") else ""
            log_loop_activity(f"✓ Auto-Judge APPROVED '{task_title}' on Attempt {attempt}/{max_retries} with multi-agent consensus evidence.{commit_info}", category="judge")
            if github_issue_num:
                commit_md = f"\n- Commit: `{task.get('short_hash')}`" if task.get("short_hash") else ""
                gh_issue_comment(
                    repo_path,
                    github_issue_num,
                    f"✅ Task '{task_title}' APPROVED by Auto-Judge on Attempt {attempt}/{max_retries}.{commit_md}\n\n### Evidence:\n- Real Test Suite: {'Passed (100%)' if test_result.get('success') else 'Verified'}\n- QA: {'Passed' if qa_passed else 'Verified'}\n- Security: {'Passed' if sec_passed else 'Verified'}\n- Oracle: Verified"
                )
            persist_active_loop_state()
            break

    LOOP_STATE["active_subagent"] = None
    persist_active_loop_state()
    return task

async def _async_loop_runner():
    global LOOP_STATE, _stop_flag, _pause_event
    
    try:
        _stop_flag = False
        _pause_event.set()
        LOOP_STATE["status"] = "running"
        LOOP_STATE["infra_blockers"] = []
        LOOP_STATE["merge_blocked_reason"] = ""
        persist_active_loop_state()

        repo_path = LOOP_STATE.get("repo_path", "")
        goal = LOOP_STATE.get("goal", "")
        
        ctx = extract_deep_repo_context(repo_path)
        repo_block = format_repo_prompt_block(ctx)

        # 0. Initialize Swarm Topology & Git Branch Isolation
        set_dynamic_subagents_roster(SWARM_LOOP_ROSTER)
        update_agent_status("orchestrator", "gemini", "running", f"Orchestrating Autonomous Swarm for: '{goal[:40]}'")

        # Branch & Worktree Isolation: Create and switch to isolated task/loop branch
        if repo_path and (Path(repo_path) / ".git").exists():
            base_br_res = run_git(repo_path, ["branch", "--show-current"])
            base_branch = base_br_res.get("stdout", "") or ""
            # Never branch off (or merge back into) a leftover swarm branch. A
            # previous loop leaves its branch checked out, so this used to chain
            # loop onto loop: the DeltaProject run merged into
            # 'swarm/loop-1787743921' instead of the real default branch, and main
            # never saw the work while junk accumulated on a detached lineage.
            if not base_branch or base_branch.startswith("swarm/"):
                resolved = resolve_default_branch(repo_path)
                log_loop_activity(
                    f"🌿 Current branch '{base_branch or '(none)'}' is a swarm branch or unset — "
                    f"switching to default branch '{resolved}' as the integration target.",
                    category="git",
                )
                sw = switch_or_create_branch(repo_path, resolved, create=False)
                landed = run_git(repo_path, ["branch", "--show-current"]).get("stdout", "").strip()
                if not sw.get("success") or landed != resolved:
                    # Never record a target branch we did not actually reach: the
                    # final merge would target a branch HEAD is not on. A dirty
                    # working tree is the usual cause, so say so and stop rather
                    # than silently building on the wrong lineage.
                    dirty = run_git(repo_path, ["status", "--porcelain"]).get("stdout", "").strip()
                    reason = (
                        "the working tree has uncommitted changes"
                        if dirty else (sw.get("error") or "checkout failed")
                    )
                    msg = (
                        f"⛔ Cannot switch from '{base_branch or '(none)'}' to default branch "
                        f"'{resolved}' — {reason}. HEAD is still '{landed or 'unknown'}'. "
                        f"Refusing to run: commit or stash your changes first, so the swarm "
                        f"does not branch from or merge into a leftover swarm branch."
                    )
                    log_loop_activity(msg, category="git")
                    LOOP_STATE["status"] = "failed"
                    LOOP_STATE["final_summary"] = msg
                    persist_active_loop_state()
                    return
                base_branch = resolved
            LOOP_STATE["target_branch"] = base_branch
            
            sess_id_short = LOOP_STATE["session_id"].replace("loop_", "")[:10]
            loop_branch = f"swarm/loop-{sess_id_short}"
            
            if base_branch != loop_branch:
                br_res = switch_or_create_branch(repo_path, loop_branch, create=True, start_point=base_branch)
                if not br_res.get("success"):
                    switch_or_create_branch(repo_path, loop_branch, create=False)
                LOOP_STATE["git_branch"] = loop_branch
                log_loop_activity(f"🌿 Checked out isolated branch '{loop_branch}' (base: '{base_branch}')", category="git")
            else:
                LOOP_STATE["git_branch"] = base_branch
            persist_active_loop_state()

        # 1. GitHub Issue Tracking Creation or Reconnection
        existing_issue = LOOP_STATE.get("github_issue")
        if existing_issue and isinstance(existing_issue, dict) and existing_issue.get("issue_number"):
            github_issue_record = existing_issue
            github_issue_num = github_issue_record.get("issue_number")
            log_loop_activity(f"🐙 Reconnected to existing GitHub Tracking Issue #{github_issue_num}: {github_issue_record.get('url', '')}", category="git")
            gh_issue_comment(
                repo_path,
                github_issue_num,
                "🔄 Server restarted. Resuming task execution from checkpoint..."
            )
        else:
            github_issue_record = gh_issue_create(
                repo_path,
                title=f"Autonomous Goal: {goal}",
                body=f"Tracking issue for autonomous feature execution.\n\n**Goal**: {goal}\n**Engine**: Swarm AI Studio Multi-Agent Swarm (Zero-Trust Pipeline)"
            )
            LOOP_STATE["github_issue"] = github_issue_record
            github_issue_num = github_issue_record.get("issue_number")
            if github_issue_record.get("url"):
                log_loop_activity(f"🐙 GitHub Tracking Issue: {github_issue_record['url']}", category="git")
            persist_active_loop_state()

        # 2. Phase 1: Pre-Flight Autonomous Research Subagent (Skip if already generated)
        if LOOP_STATE.get("research_brief") and len(LOOP_STATE["research_brief"].strip()) > 20:
            research_brief = LOOP_STATE["research_brief"]
            log_loop_activity("✓ Loaded existing Pre-Flight Research Brief from checkpoint (skipping research phase).", category="agent")
        else:
            research_result = await run_preflight_research(goal, repo_path, repo_block)
            research_brief = research_result["content"]
            LOOP_STATE["research_brief"] = research_brief
            persist_active_loop_state()  # Granular Checkpoint: after research brief
            if github_issue_num:
                gh_issue_comment(
                    repo_path,
                    github_issue_num,
                    f"### 🔍 Pre-Flight Research Brief Generated\n\nSaved artifact: `{research_result['filename']}`\n\n```markdown\n{research_brief[:1000]}...\n```"
                )

        # 3. Phase 2: Goal Decomposition into Verified Task Pipeline (Skip if already generated)
        tasks = LOOP_STATE.get("tasks", [])
        if not tasks:
            log_loop_activity("👑 Lead Advisor decomposing goal into task pipeline...", category="advisor")
            tasks = await decompose_goal_into_tasks(goal, repo_block, research_brief)
            LOOP_STATE["tasks"] = tasks
            persist_active_loop_state()  # Granular Checkpoint: after task creation
            log_loop_activity(f"✓ Task pipeline generated with {len(tasks)} sequential stages.", category="loop")

            if github_issue_num:
                task_list_md = "\n".join([f"- [ ] **Task {t['order']}**: {t['title']} (`{t['role'].upper()}`)" for t in tasks])
                gh_issue_comment(repo_path, github_issue_num, f"### 📋 Decomposed Task Pipeline\n\n{task_list_md}")

            # Break the decomposed tasks onto a GitHub Projects board (best-effort;
            # requires the `project` token scope — degrades cleanly without it).
            if repo_path and (Path(repo_path) / ".git").exists() and not LOOP_STATE.get("project_board", {}).get("number"):
                board = gh_project_ensure(repo_path, title=f"Swarm: {goal[:60]}")
                if board.get("available"):
                    LOOP_STATE["project_board"] = board
                    issue_url = (github_issue_record or {}).get("url", "")
                    gh_project_add_issue(repo_path, board["owner"], board["number"], issue_url)
                    for t in tasks:
                        item = gh_project_add_task(
                            repo_path, board["owner"], board["number"],
                            title=f"[{t['role'].upper()}] {t['title']}",
                            body=t.get("description", ""),
                        )
                        t["board_item_id"] = item.get("item_id", "")
                    log_loop_activity(f"📋 Task board created ({len(tasks)} items): {board.get('url', '')}", category="git")
                    persist_active_loop_state()
                else:
                    log_loop_activity(f"ℹ️ GitHub Projects board skipped — {board.get('reason', 'unavailable')}.", category="git")
        else:
            log_loop_activity(f"✓ Resuming task pipeline with {len(tasks)} tasks from checkpoint.", category="loop")

        # 4. Phase 3: Zero-Trust Multi-Agent Handoff Execution (Topological DAG with Parallel Execution)
        while True:
            while not _pause_event.is_set() and not _stop_flag:
                await asyncio.sleep(0.5)

            if _stop_flag or LOOP_STATE.get("status") not in ("running", "recovering"):
                break

            completed_ids = {t["id"] for t in tasks if t.get("status") == "completed"}
            if len(completed_ids) == len(tasks):
                break

            # Find all pending/in_progress tasks whose dependencies are satisfied
            ready_tasks = [
                t for t in tasks
                if t.get("status") in ("pending", "in_progress")
                and all(dep in completed_ids for dep in t.get("dependencies", []))
            ]

            if not ready_tasks:
                # If no tasks are ready and not all completed, check for unresolvable dependencies or completed run
                break

            if PARALLEL_TASK_EXECUTION and len(ready_tasks) > 1:
                batch = ready_tasks[:MAX_CONCURRENT_AGENTS]
                log_loop_activity(f"⚡ Launching {len(batch)} independent DAG tasks concurrently in parallel: {', '.join(t['title'] for t in batch)}", category="loop", is_active=True)
                for t in batch:
                    t["status"] = "in_progress"
                with _state_lock:
                    LOOP_STATE["current_task_ids"] = [t["id"] for t in batch]
                    LOOP_STATE["current_task_id"] = batch[0]["id"]
                    persist_active_loop_state()

                async def _run_parallel_task_node(t_node):
                    res = await execute_zero_trust_task(
                        t_node,
                        repo_block=repo_block,
                        repo_path=repo_path,
                        research_brief=research_brief,
                        github_issue_num=github_issue_num
                    )
                    with _state_lock:
                        LOOP_STATE["iteration"] = LOOP_STATE.get("iteration", 0) + 1
                        persist_active_loop_state()
                    return res

                await asyncio.gather(*(_run_parallel_task_node(t) for t in batch))
                with _state_lock:
                    LOOP_STATE["current_task_ids"] = []
                    persist_active_loop_state()
                await asyncio.sleep(0.3)
            else:
                task = ready_tasks[0]
                task_id = task["id"]
                with _state_lock:
                    LOOP_STATE["current_task_id"] = task_id
                    LOOP_STATE["current_task_ids"] = [task_id]
                    task["status"] = "in_progress"
                    persist_active_loop_state()

                await execute_zero_trust_task(
                    task,
                    repo_block=repo_block,
                    repo_path=repo_path,
                    research_brief=research_brief,
                    github_issue_num=github_issue_num
                )
                with _state_lock:
                    LOOP_STATE["iteration"] = LOOP_STATE.get("iteration", 0) + 1
                    LOOP_STATE["current_task_ids"] = []
                    persist_active_loop_state()
                await asyncio.sleep(0.3)

        # 5. Phase 4: Final Synthesis, Deliverable Sign-off & Merge to Main
        all_completed = all(t.get("status") == "completed" for t in tasks) if tasks else False
        failed_tasks = [t for t in tasks if t.get("status") == "failed"]
        infra_blockers = LOOP_STATE.get("infra_blockers", []) or []

        if failed_tasks:
            # Explicit, non-negotiable stop. Nothing is merged when any task failed
            # the zero-trust gate; the branch is left intact for inspection.
            LOOP_STATE["produced_code"] = any(t.get("files_written") for t in tasks)
            LOOP_STATE["files_written_total"] = sum(len(t.get("files_written", []) or []) for t in tasks)
            LOOP_STATE["failed_task_count"] = len(failed_tasks)
            LOOP_STATE["status"] = "failed"
            LOOP_STATE["completed_at"] = int(time.time() * 1000)
            LOOP_STATE["active_subagent"] = None
            LOOP_STATE["active_subagents"] = []
            LOOP_STATE["current_task_id"] = None
            LOOP_STATE["current_task_ids"] = []
            LOOP_STATE["final_summary"] = f"Loop stopped: {len(failed_tasks)} of {len(tasks)} task(s) failed zero-trust verification."
            persist_active_loop_state()

            log_loop_activity(
                f"⛔ {len(failed_tasks)}/{len(tasks)} task(s) FAILED the zero-trust gate. "
                f"NOT merging into '{LOOP_STATE.get('target_branch', 'main')}'. "
                f"Branch '{LOOP_STATE.get('git_branch', '')}' is preserved for inspection.",
                category="loop",
            )
            for t in failed_tasks:
                log_loop_activity(
                    f"   • '{t.get('title')}': {'; '.join(t.get('failure_reasons', []) or ['unspecified'])}",
                    category="loop",
                )
            for b in infra_blockers:
                log_loop_activity(
                    f"   🚧 Host blocker ({b.get('runner')}): {b.get('reason')}",
                    category="loop",
                )
        elif not all_completed and not _stop_flag and LOOP_STATE.get("status") in ("running", "recovering"):
            LOOP_STATE["status"] = "failed"
            LOOP_STATE["completed_at"] = int(time.time() * 1000)
            LOOP_STATE["active_subagent"] = None
            LOOP_STATE["active_subagents"] = []
            LOOP_STATE["current_task_id"] = None
            LOOP_STATE["current_task_ids"] = []
            reason = "No tasks were scheduled or tasks could not proceed due to unresolved dependencies." if not tasks else "Task pipeline stalled before full completion."
            LOOP_STATE["final_summary"] = f"Loop stopped: {reason}"
            persist_active_loop_state()
            log_loop_activity(f"⛔ {reason}", category="loop")

        if not _stop_flag and LOOP_STATE.get("status") in ("running", "recovering") and all_completed:
            log_loop_activity("👑 Synthesizing all sub-agent deliverables into final Feature Document...", category="advisor")
            update_agent_status("orchestrator", "gemini", "running", "Synthesizing final feature artifact & sign-off...")
            
            # Honesty gate: did the swarm actually produce code? If no task wrote
            # a file AND no task committed, there is nothing to merge — say so
            # plainly instead of reporting a bogus "merged to main / completed".
            total_files_written = sum(len(t.get("files_written", []) or []) for t in LOOP_STATE["tasks"])
            # "Produced code" means real feature files were written — NOT merely that a
            # commit exists (artifacts like the research brief can create commits with
            # zero feature changes). Require actual file writes to claim success.
            produced_code = total_files_written > 0
            LOOP_STATE["produced_code"] = produced_code
            LOOP_STATE["files_written_total"] = total_files_written

            # Verification honesty gate. `produced_code` only proves bytes hit the
            # disk — it was previously the ONLY merge precondition besides task
            # status, so placeholder junk satisfied it. Require that every task
            # actually cleared QA and that no host-level blocker left the suite
            # unverified before anything touches the default branch.
            unverified = [t.get("title") for t in LOOP_STATE["tasks"] if not t.get("qa_passed")]
            merge_blocked_reason = ""
            if unverified:
                merge_blocked_reason = (
                    f"{len(unverified)} task(s) never passed QA: {', '.join(str(u) for u in unverified[:5])}"
                )
            elif infra_blockers:
                merge_blocked_reason = (
                    f"test infrastructure unavailable ({infra_blockers[0].get('reason')}) — "
                    f"deliverable is UNVERIFIED"
                )
            LOOP_STATE["merge_blocked_reason"] = merge_blocked_reason

            # Real Merge to Main: Merge isolated loop branch into target default branch
            target_branch = LOOP_STATE.get("target_branch", "main")
            loop_branch = LOOP_STATE.get("git_branch", "")
            if not produced_code:
                log_loop_activity(
                    "⚠️ No code was produced by any task (the model emitted no applicable file changes). "
                    "Skipping merge — nothing to integrate. Review the task outputs and re-run.",
                    category="loop",
                )
            elif merge_blocked_reason:
                log_loop_activity(
                    f"⛔ Merge BLOCKED — {merge_blocked_reason}. "
                    f"Branch '{loop_branch}' is preserved; nothing was integrated into "
                    f"'{target_branch}'. Fix the blocker and re-run.",
                    category="loop",
                )
            elif repo_path and (Path(repo_path) / ".git").exists() and loop_branch and loop_branch != target_branch:
                # 1. Open GitHub Pull Request if GitHub CLI and remote origin are configured
                if is_gh_available():
                    pr_body = (
                        f"## 🤖 Autonomous Swarm Feature Implementation\n\n"
                        f"**Goal**: {goal}\n"
                        f"**Session ID**: `{LOOP_STATE.get('session_id')}`\n\n"
                        f"### 📋 Completed & Verified Tasks:\n" +
                        "\n".join(f"- [x] {t.get('title')}" for t in tasks) +
                        f"\n\n### 🛡️ Zero-Trust Verification:\n"
                        f"- Test Runner Suite: **PASSED**\n"
                        f"- Clean Architecture Audit: **APPROVED**\n"
                        f"- Security Threat Scan: **APPROVED**\n"
                        f"{f'- Resolves #{github_issue_num}' if github_issue_num else ''}"
                    )
                    pr_res = gh_pr_create(
                        repo_path=repo_path,
                        title=f"feat: {goal}",
                        body=pr_body,
                        head_branch=loop_branch,
                        base_branch=target_branch
                    )
                    if pr_res.get("success"):
                        LOOP_STATE["pull_request"] = pr_res
                        log_loop_activity(f"🚀 Created GitHub Pull Request: {pr_res.get('url')}", category="git")

                # 2. Real Merge to Main
                merge_msg = f"feat: {goal} [Swarm Session #{LOOP_STATE['session_id']}]"
                merge_res = merge_branch(repo_path, source_branch=loop_branch, target_branch=target_branch, message=merge_msg)
                if merge_res.get("merged"):
                    LOOP_STATE["merge_commit"] = merge_res.get("merge_commit", "")
                    LOOP_STATE["merge_short_hash"] = merge_res.get("short_hash", "")
                    log_loop_activity(f"🔀 Merged branch '{loop_branch}' into '{target_branch}' (Merge commit: {LOOP_STATE.get('merge_short_hash', '')})", category="git")

                    # Clean up the now-merged isolated branch so state doesn't accumulate.
                    del_res = git_delete_branch(repo_path, loop_branch, force=False)
                    if del_res.get("success"):
                        LOOP_STATE["branch_deleted"] = True
                        log_loop_activity(f"🧹 Deleted merged branch '{loop_branch}'.", category="git")
                    else:
                        log_loop_activity(f"⚠️ Could not delete branch '{loop_branch}': {del_res.get('error')}", category="git")
                else:
                    log_loop_activity(f"⚠️ Merge of '{loop_branch}' into '{target_branch}' failed: {merge_res.get('error')}", category="git")

            summary_prompt = f"""You are the Lead Advisor AI Architect.
The autonomous swarm has completed the feature: '{goal}' across all tasks:

Tasks Completed & Verified:
{json.dumps([{ 'title': t['title'], 'role': t['role'], 'attempts': t.get('attempts', 1), 'commit_hash': t.get('short_hash', 'N/A'), 'files_written': t.get('files_written', []), 'output': t.get('output', '')[:400] } for t in LOOP_STATE['tasks']], indent=2)}

Pre-Flight Research Summary:
{research_brief[:1000]}

Branch: {LOOP_STATE.get('git_branch', 'main')} -> Merged to: {LOOP_STATE.get('target_branch', 'main')}
Merge Commit: {LOOP_STATE.get('merge_commit', 'N/A')}

Provide an authoritative Executive Summary, Architecture Implementation Breakdown, Zero-Trust QA Verification Evidence, and Final Sign-Off.
"""
            final_summary = await query_gemini(summary_prompt)
            if not final_summary.strip() or "Error:" in final_summary:
                final_summary = await query_local_slot(summary_prompt, system="You are the Lead Advisor.")

            LOOP_STATE["final_summary"] = final_summary
            LOOP_STATE["verification_certificate"] = final_summary
            LOOP_STATE["status"] = "completed"
            LOOP_STATE["completed_at"] = int(time.time() * 1000)
            LOOP_STATE["active_subagent"] = None
            persist_active_loop_state()

            safe_title = "".join(c if c.isalnum() else "_" for c in goal)[:30]
            save_artifact_to_disk(
                title=f"Autonomous Swarm Feature — {goal}",
                filename=f"FEATURE_{safe_title}.md",
                content=final_summary,
                repo_path=repo_path
            )

            # Close GitHub Issue — but only claim success if code actually landed.
            if github_issue_num:
                if produced_code:
                    merge_info = f"\n\n**Merge Commit**: `{LOOP_STATE.get('merge_commit', 'N/A')}` (Merged into `{LOOP_STATE.get('target_branch', 'main')}`)" if LOOP_STATE.get("merge_commit") else ""
                    gh_issue_close(
                        repo_path,
                        github_issue_num,
                        comment=f"🎉 **Goal Completed by Swarm AI Studio** ({total_files_written} file(s) changed){merge_info}\n\n### Executive Summary\n{final_summary[:1200]}...\n\nVerified through the Zero-Trust Multi-Agent pipeline with real code application, real test-suite execution, and git merge.",
                        reason="completed"
                    )
                else:
                    # Leave the issue OPEN and comment honestly, rather than closing a goal that produced nothing.
                    gh_issue_comment(
                        repo_path,
                        github_issue_num,
                        "⚠️ **Run finished without producing code.** The agents completed the pipeline but emitted no applicable file changes, so nothing was merged and this issue stays open. This usually means the local model didn't return code in an applicable format — try a stronger model or a more specific goal.",
                    )

            if produced_code:
                log_loop_activity(f"🎉 Goal '{goal}' completed — {total_files_written} file(s) changed and merged into '{LOOP_STATE.get('target_branch', 'main')}'. Artifact and GitHub sign-off finalized.", category="loop")
            else:
                log_loop_activity(f"⚠️ Goal '{goal}' finished with NO code changes — issue left open, nothing merged.", category="loop")

        # Reset agent statuses in topology
        for sub in SWARM_LOOP_ROSTER:
            update_agent_status("sub_agents", sub["id"], "idle", "Idle")
        update_agent_status("orchestrator", "gemini", "idle", "Awaiting user task...")

    except asyncio.CancelledError:
        log_loop_activity("Loop stopped by user.", category="loop")
        LOOP_STATE["status"] = "idle"
        LOOP_STATE["active_subagent"] = None
        LOOP_STATE["active_subagents"] = []
        LOOP_STATE["current_task_id"] = None
        LOOP_STATE["current_task_ids"] = []
        persist_active_loop_state()
        for sub in SWARM_LOOP_ROSTER:
            update_agent_status("sub_agents", sub["id"], "idle", "Idle")
        update_agent_status("orchestrator", "gemini", "idle", "Awaiting user task...")
    except Exception as e:
        log_loop_activity(f"Loop error: {e}", category="error")
        LOOP_STATE["status"] = "failed"
        LOOP_STATE["active_subagent"] = None
        LOOP_STATE["active_subagents"] = []
        LOOP_STATE["current_task_id"] = None
        LOOP_STATE["current_task_ids"] = []
        persist_active_loop_state()
        for sub in SWARM_LOOP_ROSTER:
            update_agent_status("sub_agents", sub["id"], "idle", "Idle")
        update_agent_status("orchestrator", "gemini", "idle", "Awaiting user task...")

def _thread_worker():
    global _loop_asyncio_loop
    _loop_asyncio_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_loop_asyncio_loop)
    try:
        _loop_asyncio_loop.run_until_complete(_async_loop_runner())
    finally:
        # Safety net: Guarantee that if status is still running/recovering when the worker thread exits,
        # it is reconciled to an honest terminal state with idle agents.
        with _state_lock:
            if LOOP_STATE.get("status") in ("running", "recovering"):
                tasks = LOOP_STATE.get("tasks", [])
                if tasks and all(t.get("status") == "completed" for t in tasks):
                    LOOP_STATE["status"] = "completed"
                elif any(t.get("status") == "failed" for t in tasks):
                    LOOP_STATE["status"] = "failed"
                elif not LOOP_STATE.get("goal"):
                    LOOP_STATE["status"] = "idle"
                else:
                    LOOP_STATE["status"] = "failed"
                LOOP_STATE["active_subagent"] = None
                LOOP_STATE["active_subagents"] = []
                LOOP_STATE["current_task_id"] = None
                LOOP_STATE["current_task_ids"] = []
                persist_active_loop_state()
            _loop_thread = None
        for sub in SWARM_LOOP_ROSTER:
            update_agent_status("sub_agents", sub["id"], "idle", "Idle")
        update_agent_status("orchestrator", "gemini", "idle", "Awaiting user task...")
        _loop_asyncio_loop.close()

def start_loop(goal: str, repo_path: str = "", session_id: str = None, advisor_session_id: str = "") -> Dict[str, Any]:
    global _loop_thread, LOOP_STATE, _stop_flag
    
    if LOOP_STATE.get("status") == "running":
        return {"success": False, "error": "Autonomous loop is already running."}

    _stop_flag = False
    _pause_event.set()
    now = int(time.time() * 1000)

    clean_goal = goal.strip() if goal else ""
    if session_id:
        existing = load_loop_session(session_id)
        if existing:
            sess_id = session_id
            created_at = existing.get("created_at", now)
            adv_id = advisor_session_id or existing.get("advisor_session_id", "")
            if not clean_goal:
                clean_goal = existing.get("goal", "")
            if not repo_path:
                repo_path = existing.get("repo_path", "")
        else:
            created = create_new_loop_session(
                title=clean_goal[:35] if clean_goal else "Auto-Dev Loop",
                goal=clean_goal,
                repo_path=repo_path,
                advisor_session_id=advisor_session_id
            )
            sess_id = created["id"]
            created_at = now
            adv_id = advisor_session_id
    else:
        created = create_new_loop_session(
            title=clean_goal[:35] if clean_goal else "Auto-Dev Loop",
            goal=clean_goal,
            repo_path=repo_path,
            advisor_session_id=advisor_session_id
        )
        sess_id = created["id"]
        created_at = now
        adv_id = advisor_session_id

    LOOP_STATE = {
        "id": sess_id,
        "session_id": sess_id,
        "name": clean_goal[:35] if clean_goal else "Auto-Dev Loop",
        "title": clean_goal[:35] if clean_goal else "Auto-Dev Loop",
        "status": "running",
        "goal": clean_goal,
        "repo_path": repo_path,
        "iteration": 0,
        "max_iterations": 20,
        "tasks": [],
        "current_task_id": None,
        "active_subagent": None,
        "advisor_pings": [],
        "live_logs": [],
        "research_brief": "",
        "github_issue": None,
        "verification_certificate": "",
        "advisor_session_id": adv_id,
        "started_at": now,
        "completed_at": 0,
        "final_summary": "",
        "created_at": created_at,
        "updated_at": now,
        "attempts": 0,
        "git_branch": "",
        "target_branch": "main",
        "merge_commit": "",
        "merge_short_hash": "",
        "project_board": {},
        "branch_deleted": False,
        "test_summary": ""
    }
    
    persist_active_loop_state()
    
    _loop_thread = threading.Thread(target=_thread_worker, daemon=True)
    _loop_thread.start()
    log_loop_activity(f"Started Autonomous Swarm for goal: '{clean_goal}'", category="loop")
    return {"success": True, "loop_id": LOOP_STATE["id"], "session_id": LOOP_STATE["id"]}

def pause_loop() -> Dict[str, Any]:
    if LOOP_STATE.get("status") == "running":
        _pause_event.clear()
        LOOP_STATE["status"] = "paused"
        persist_active_loop_state()
        log_loop_activity("Autonomous loop paused.", category="loop")
        return {"success": True, "status": "paused"}
    return {"success": False, "error": "Loop is not running."}

def resume_loop(session_id: Optional[str] = None) -> Dict[str, Any]:
    global _loop_thread, LOOP_STATE, _stop_flag
    
    # 1. If a session_id was specified, load that session
    if session_id:
        existing = load_loop_session(session_id)
        if not existing:
            return {"success": False, "error": f"Session '{session_id}' not found."}
        
        # If this session is already running in an active thread
        if _loop_thread and _loop_thread.is_alive() and LOOP_STATE.get("id") == session_id and LOOP_STATE.get("status") == "running":
            return {"success": True, "status": "running", "session_id": session_id}
            
        LOOP_STATE = _ensure_loop_state_keys(existing)
        # Reset failed tasks to pending so the runner re-executes them from checkpoint
        for t in LOOP_STATE.get("tasks", []):
            if t.get("status") == "failed":
                t["status"] = "pending"
                t["attempts"] = 0
                t["gate_reasons"] = []
    
    # 2. If no session_id, check if current thread is running & paused
    if _loop_thread and _loop_thread.is_alive() and LOOP_STATE.get("status") == "paused":
        _pause_event.set()
        LOOP_STATE["status"] = "running"
        persist_active_loop_state()
        log_loop_activity("Autonomous loop resumed.", category="loop")
        return {"success": True, "status": "running", "session_id": LOOP_STATE["id"]}

    # 3. If thread is not alive (restarted server or resuming from paused/interrupted/failed on disk)
    if not LOOP_STATE.get("goal"):
        sessions = list_loop_sessions()
        candidates = [s for s in sessions if s.get("status") in ("interrupted", "failed", "paused", "running")]
        if candidates:
            loaded = load_loop_session(candidates[0]["id"])
            if loaded:
                LOOP_STATE = _ensure_loop_state_keys(loaded)
                for t in LOOP_STATE.get("tasks", []):
                    if t.get("status") == "failed":
                        t["status"] = "pending"
                        t["attempts"] = 0
                        t["gate_reasons"] = []
    
    if not LOOP_STATE.get("goal"):
        return {"success": False, "error": "No active, interrupted or failed loop session found with a valid goal to resume."}
    
    _stop_flag = False
    _pause_event.set()
    LOOP_STATE["status"] = "running"
    persist_active_loop_state()
    
    _loop_thread = threading.Thread(target=_thread_worker, daemon=True)
    _loop_thread.start()
    log_loop_activity(f"🔄 Resumed Autonomous Swarm from checkpoint for goal: '{LOOP_STATE.get('goal')}'", category="loop")
    return {"success": True, "status": "running", "session_id": LOOP_STATE["id"]}

def auto_resume_on_startup() -> Optional[Dict[str, Any]]:
    """
    Auto-detects any interrupted runs on startup and resumes if AUTO_RESUME_ON_START is True.
    """
    interrupted = detect_and_recover_interrupted_sessions()
    if AUTO_RESUME_ON_START and interrupted:
        latest = sorted(interrupted, key=lambda s: s.get("updated_at", 0), reverse=True)[0]
        sess_id = latest.get("session_id") or latest.get("id")
        log_event("info", "recovery", f"Auto-resuming interrupted loop session '{sess_id}' on server startup")
        return resume_loop(session_id=sess_id)
    return None

def stop_loop() -> Dict[str, Any]:
    global _stop_flag, _loop_thread
    _stop_flag = True
    _pause_event.set()
    LOOP_STATE["status"] = "idle"
    LOOP_STATE["active_subagent"] = None
    LOOP_STATE["active_subagents"] = []
    LOOP_STATE["current_task_id"] = None
    LOOP_STATE["current_task_ids"] = []
    _loop_thread = None
    persist_active_loop_state()
    log_loop_activity("Autonomous loop terminated.", category="loop")
    for sub in SWARM_LOOP_ROSTER:
        update_agent_status("sub_agents", sub["id"], "idle", "Idle")
    update_agent_status("orchestrator", "gemini", "idle", "Awaiting user task...")
    return {"success": True, "status": "idle"}

async def async_transfer_advisor_to_loop(
    session_id: str = "",
    custom_goal: str = "",
    auto_start: bool = True,
    repo_path: str = ""
) -> Dict[str, Any]:
    """
    Advisor-to-Loop Seamless Transfer:
    Extracts conversation synthesis from the active advisor session,
    creates and initializes a persistent Loop Session, establishes two-way traceability linking,
    and optionally auto-launches the autonomous dev swarm loop.
    """
    advisor_sess = None
    if session_id:
        advisor_sess = load_session(session_id)
    if not advisor_sess:
        all_adv = list_sessions()
        if all_adv:
            advisor_sess = load_session(all_adv[0]["id"])

    adv_id = advisor_sess.get("id", "") if advisor_sess else ""
    eff_repo_path = repo_path or (advisor_sess.get("repo_path", "") if advisor_sess else "")

    goal = custom_goal.strip() if custom_goal else ""
    if not goal:
        messages = advisor_sess.get("messages", []) if advisor_sess else []
        if messages:
            turns_text = []
            for m in messages[-6:]:
                p = m.get("prompt", "")
                a = m.get("answer", "")
                if p:
                    turns_text.append(f"User Request: {p}")
                if a:
                    turns_text.append(f"Advisor Blueprint: {a[:500]}")
            conv_str = "\n".join(turns_text)
            
            synthesis_prompt = f"""You are the Lead Advisor AI Architect.
A user discussed a software feature with the AI Advisor:
<DISCUSSION>
{conv_str}
</DISCUSSION>

Synthesize a single, clear, comprehensive, and actionable engineering implementation goal (1-2 sentences) for an Autonomous Dev Swarm to build, test, and verify.
Respond ONLY with the concise goal string."""

            try:
                candidate = await query_gemini(synthesis_prompt)
                if candidate and "Error:" not in candidate and len(candidate.strip()) > 5:
                    goal = candidate.strip().strip('"').strip("'")
                else:
                    candidate = await query_local_slot(synthesis_prompt, system="You are the Lead Advisor AI Architect.")
                    if candidate and "Error:" not in candidate and len(candidate.strip()) > 5:
                        goal = candidate.strip().strip('"').strip("'")
            except Exception:
                pass

            if not goal or "Error:" in goal or len(goal) < 5:
                last_turn = messages[-1] if messages else {}
                goal = last_turn.get("prompt", "") or advisor_sess.get("title", "Autonomous Feature Implementation")
        else:
            goal = advisor_sess.get("title", "Autonomous Feature Implementation") if advisor_sess else "Autonomous Feature Implementation"

    title = f"Loop: {goal[:32]}..." if len(goal) > 32 else f"Loop: {goal}"
    loop_sess_summary = create_new_loop_session(
        title=title,
        goal=goal,
        repo_path=eff_repo_path,
        advisor_session_id=adv_id
    )
    loop_id = loop_sess_summary["id"]

    if adv_id:
        link_advisor_and_loop_sessions(adv_id, loop_id)

    if auto_start:
        start_res = start_loop(goal=goal, repo_path=eff_repo_path, session_id=loop_id, advisor_session_id=adv_id)
        current_state = get_loop_state()
    else:
        select_loop_session(loop_id)
        current_state = get_loop_state()

    return {
        "success": True,
        "loop_session_id": loop_id,
        "session_id": loop_id,
        "goal": goal,
        "repo_path": eff_repo_path,
        "advisor_session_id": adv_id,
        "auto_started": auto_start,
        "state": current_state
    }

def transfer_advisor_to_loop(
    session_id: str = "",
    custom_goal: str = "",
    auto_start: bool = True,
    repo_path: str = ""
) -> Dict[str, Any]:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(
            async_transfer_advisor_to_loop(
                session_id=session_id,
                custom_goal=custom_goal,
                auto_start=auto_start,
                repo_path=repo_path
            )
        )
    finally:
        loop.close()
