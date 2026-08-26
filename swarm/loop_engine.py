"""
Autonomous Loop Agent Engine (Auto-Dev Swarm)
Decomposes goals, creates task pipelines (PM/Dev/QA/Review), assigns sub-agents across
GPU slots, and provides real-time Lead Advisor escalation (Smartest Model Ping).
"""

import asyncio
import threading
import time
import json
import uuid
from pathlib import Path
from typing import List, Dict, Any, Optional
from swarm.logger import log_event
from swarm.git_engine import extract_deep_repo_context, format_repo_prompt_block, run_git
from swarm.model_scout import load_model_assignments
from swarm.artifacts import save_artifact_to_disk

# Global Autonomous Loop State
LOOP_STATE: Dict[str, Any] = {
    "id": "",
    "status": "idle", # idle, running, paused, completed, error
    "goal": "",
    "repo_path": "",
    "iteration": 0,
    "max_iterations": 20,
    "tasks": [],
    "current_task_id": None,
    "active_subagent": None,
    "advisor_pings": [],
    "live_logs": [],
    "started_at": 0,
    "completed_at": 0,
    "final_summary": ""
}

_loop_thread: Optional[threading.Thread] = None
_loop_asyncio_loop: Optional[asyncio.AbstractEventLoop] = None
_pause_event = threading.Event()
_pause_event.set()
_stop_flag = False

def get_loop_state() -> Dict[str, Any]:
    return LOOP_STATE

def log_loop_activity(message: str, category: str = "loop", is_active: bool = False):
    timestamp = time.strftime('%H:%M:%S', time.localtime())
    entry = {
        "timestamp": timestamp,
        "message": message,
        "category": category,
        "is_active": is_active
    }
    LOOP_STATE["live_logs"].append(entry)
    if len(LOOP_STATE["live_logs"]) > 100:
        LOOP_STATE["live_logs"].pop(0)
    log_event("info", "loop", message)

async def ping_lead_advisor(subagent_name: str, role: str, question: str, task_context: str = "") -> str:
    """
    Sub-agent escalation mechanism:
    If a sub-agent has questions, doubts, compiler errors, or architecture ambiguities,
    they ping the Gemini Lead Advisor (the smartest model) to get authoritative guidance.
    """
    from swarm.orchestrator import query_gemini
    
    t0 = time.time()
    log_loop_activity(f"📡 {subagent_name} ({role}) pinged Lead Advisor: '{question[:60]}...'", category="ping")
    
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
    
    return answer

async def decompose_goal_into_tasks(goal: str, repo_block: str) -> List[Dict[str, Any]]:
    """Uses Lead Advisor to plan and break down the goal into verifiable tasks."""
    from swarm.orchestrator import query_gemini
    
    prompt = f"""You are the Chief Product & Software Architect.
Goal: {goal}

{repo_block}

Break this goal down into 3 to 6 atomic, sequential vertical slice tasks.
Assign each task a specialized role from:
- 'pm' (Requirements & Specification)
- 'dev' (Implementation & Code Construction)
- 'qa' (Syntax Verification & Test Validation)
- 'review' (Security Audit & Blast Radius Review)

Respond ONLY with a valid JSON array of objects with this schema:
[
  {{
    "title": "Task Title",
    "role": "pm" | "dev" | "qa" | "review",
    "description": "What to do and target files",
    "acceptance_criteria": "How to verify this is done"
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
                "title": f"Specification & Architecture for '{goal}'",
                "role": "pm",
                "description": "Define data contracts, endpoints, and architectural boundaries.",
                "acceptance_criteria": "Architecture blueprint finalized."
            },
            {
                "title": f"Implementation of '{goal}'",
                "role": "dev",
                "description": "Draft code changes and file implementations.",
                "acceptance_criteria": "All target files written with error handling."
            },
            {
                "title": f"QA, LSP & Compiler Verification",
                "role": "qa",
                "description": "Check syntax, compile targets, and verify test assertions.",
                "acceptance_criteria": "Zero syntax errors and tests passing."
            },
            {
                "title": f"Security & Regression Review",
                "role": "review",
                "description": "Audit security vectors, injection risks, and blast radius.",
                "acceptance_criteria": "Zero high-severity vulnerabilities."
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

        formatted_tasks.append({
            "id": f"task-{i+1}",
            "order": i + 1,
            "title": t.get("title", f"Task {i+1}"),
            "role": role,
            "description": t.get("description", ""),
            "acceptance_criteria": t.get("acceptance_criteria", ""),
            "status": "pending",
            "assigned_agent": agent_name,
            "assigned_slot": slot,
            "output": "",
            "advisor_consultations": []
        })

    return formatted_tasks

async def execute_task_step(task: Dict[str, Any], repo_block: str) -> Dict[str, Any]:
    from swarm.orchestrator import query_local_slot
    
    role = task["role"]
    agent_name = task["assigned_agent"]
    
    log_loop_activity(f"🚀 Sub-agent [{agent_name}] started: '{task['title']}'", category="agent", is_active=True)
    LOOP_STATE["active_subagent"] = {
        "name": agent_name,
        "role": role,
        "task_title": task["title"],
        "slot": task["assigned_slot"],
        "status": "thinking"
    }

    if role in ["dev", "review"]:
        consult_question = f"For task '{task['title']}', what are the essential edge cases, performance invariants, and production best practices we must enforce?"
        advisor_guidance = await ping_lead_advisor(agent_name, role, consult_question, task_context=task['description'])
        task["advisor_consultations"].append({
            "question": consult_question,
            "guidance": advisor_guidance
        })
    else:
        advisor_guidance = ""

    prompt = f"""{repo_block}

Task: {task['title']}
Role: {role.upper()}
Description: {task['description']}
Acceptance Criteria: {task['acceptance_criteria']}

Lead Advisor Guidance:
{advisor_guidance}

Execute this step rigorously. Provide concrete code, validation results, and complete implementation details.
"""
    system_prompt = f"You are {agent_name} specialized in {role.upper()}. Follow the Lead Advisor guidance precisely."
    output = await query_local_slot(prompt, system=system_prompt)
    
    task["output"] = output
    task["status"] = "completed"
    
    log_loop_activity(f"✓ [{agent_name}] finished task '{task['title']}'", category="agent")
    return task

async def _async_loop_runner():
    global LOOP_STATE, _stop_flag
    
    try:
        repo_path = LOOP_STATE["repo_path"]
        goal = LOOP_STATE["goal"]
        
        ctx = extract_deep_repo_context(repo_path)
        repo_block = format_repo_prompt_block(ctx)

        # 1. PM Phase: Decompose Goal into Tasks
        log_loop_activity("👑 Lead Advisor decomposing goal into task pipeline...", category="advisor")
        tasks = await decompose_goal_into_tasks(goal, repo_block)
        LOOP_STATE["tasks"] = tasks
        log_loop_activity(f"✓ Task pipeline generated with {len(tasks)} sequential stages.", category="loop")

        # 2. Continuous Loop Execution
        for task in tasks:
            while not _pause_event.is_set() and not _stop_flag:
                await asyncio.sleep(0.5)

            if _stop_flag or LOOP_STATE["status"] != "running":
                break

            task_id = task["id"]
            LOOP_STATE["current_task_id"] = task_id
            task["status"] = "in_progress"
            
            await execute_task_step(task, repo_block)
            LOOP_STATE["iteration"] += 1
            
            await asyncio.sleep(0.5)

        # 3. Final Synthesis & Artifact Generation
        if not _stop_flag and LOOP_STATE["status"] == "running":
            log_loop_activity("👑 Synthesizing all sub-agent deliverables into final Feature Document...", category="advisor")
            from swarm.orchestrator import query_gemini
            
            summary_prompt = f"""You are the Lead Advisor.
The autonomous swarm has completed the feature: '{goal}' across all tasks:

Tasks Completed:
{json.dumps([{ 'title': t['title'], 'role': t['role'], 'output': t['output'][:400] } for t in LOOP_STATE['tasks']], indent=2)}

Provide an Executive Summary, Full Implementation Spec, and QA Verification Sign-off.
"""
            final_summary = await query_gemini(summary_prompt)
            LOOP_STATE["final_summary"] = final_summary
            LOOP_STATE["status"] = "completed"
            LOOP_STATE["completed_at"] = int(time.time() * 1000)
            LOOP_STATE["active_subagent"] = None

            safe_title = "".join(c if c.isalnum() else "_" for c in goal)[:30]
            save_artifact_to_disk(
                title=f"Autonomous Swarm Feature — {goal}",
                filename=f"FEATURE_{safe_title}.md",
                content=final_summary,
                repo_path=repo_path
            )
            log_loop_activity(f"🎉 Goal '{goal}' completed successfully! Artifact generated.", category="loop")

    except asyncio.CancelledError:
        log_loop_activity("Loop stopped by user.", category="loop")
        LOOP_STATE["status"] = "idle"
    except Exception as e:
        log_loop_activity(f"Loop error: {e}", category="error")
        LOOP_STATE["status"] = "error"

def _thread_worker():
    global _loop_asyncio_loop
    _loop_asyncio_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_loop_asyncio_loop)
    try:
        _loop_asyncio_loop.run_until_complete(_async_loop_runner())
    finally:
        _loop_asyncio_loop.close()

def start_loop(goal: str, repo_path: str = "") -> Dict[str, Any]:
    global _loop_thread, LOOP_STATE, _stop_flag
    
    if LOOP_STATE["status"] == "running":
        return {"success": False, "error": "Autonomous loop is already running."}

    _stop_flag = False
    _pause_event.set()

    LOOP_STATE = {
        "id": f"loop-{uuid.uuid4().hex[:8]}",
        "status": "running",
        "goal": goal.strip(),
        "repo_path": repo_path,
        "iteration": 0,
        "max_iterations": 20,
        "tasks": [],
        "current_task_id": None,
        "active_subagent": None,
        "advisor_pings": [],
        "live_logs": [],
        "started_at": int(time.time() * 1000),
        "completed_at": 0,
        "final_summary": ""
    }
    
    _loop_thread = threading.Thread(target=_thread_worker, daemon=True)
    _loop_thread.start()
    log_loop_activity(f"Started Autonomous Swarm for goal: '{goal}'", category="loop")
    return {"success": True, "loop_id": LOOP_STATE["id"]}

def pause_loop() -> Dict[str, Any]:
    if LOOP_STATE["status"] == "running":
        _pause_event.clear()
        LOOP_STATE["status"] = "paused"
        log_loop_activity("Autonomous loop paused.", category="loop")
        return {"success": True, "status": "paused"}
    return {"success": False, "error": "Loop is not running."}

def resume_loop() -> Dict[str, Any]:
    if LOOP_STATE["status"] == "paused":
        _pause_event.set()
        LOOP_STATE["status"] = "running"
        log_loop_activity("Autonomous loop resumed.", category="loop")
        return {"success": True, "status": "running"}
    return {"success": False, "error": "Loop is not paused."}

def stop_loop() -> Dict[str, Any]:
    global _stop_flag
    _stop_flag = True
    _pause_event.set()
    LOOP_STATE["status"] = "idle"
    LOOP_STATE["active_subagent"] = None
    log_loop_activity("Autonomous loop terminated.", category="loop")
    return {"success": True, "status": "idle"}
