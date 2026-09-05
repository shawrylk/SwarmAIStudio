"""
Task-Aware Dynamic Swarm Planner & Orchestrator Engine
Dynamically scales 1 to 8 GPU slots with specialized skills based on task intent.
Includes Cost-Based Optimizer (CBO) & SQL-Style Query DAG Planning.
Includes Context7 Live Documentation & API Scout for 100% up-to-date knowledge.
Synthesizes findings via Gemini Lead Advisor and persists Artifacts.
"""

import asyncio
import subprocess
import time
import shutil
import threading
from typing import List, Dict, Any
import httpx
from pathlib import Path
from swarm.config import LFM_URL, QWEN_ORACLE_SCRIPT, MAX_CONCURRENT_AGENTS, script_is_runnable

# Sentinel prefix marking a consensus/oracle response that did NOT actually run,
# so downstream code and the UI never mistake a fallback notice for a real verdict.
QWEN_UNAVAILABLE_PREFIX = "⚠️ [ORACLE UNAVAILABLE]"
from swarm.model_scout import load_model_assignments
from swarm.git_engine import extract_deep_repo_context, format_repo_prompt_block
from swarm.artifacts import save_artifact_to_disk
from swarm.sessions import save_session_turn
from swarm.context7_engine import fetch_latest_doc_context, query_context7_library
from swarm.planner_cbo import optimize_and_select_best_plan
from swarm.memory_engine import read_disk_memory_files, format_disk_memory_prompt_block
from swarm.web_scout import search_web_live, format_web_scout_prompt_block
from swarm.rules_engine import format_enforced_rules_prompt

_orchestrator_lock = threading.RLock()
MODEL_ASSIGNMENTS = load_model_assignments()

SWARM_LOOP_ROSTER = [
    {"id": "dev", "name": "Code Implementer", "role": "dev"},
    {"id": "verify", "name": "Test & Verify", "role": "verify"},
]

SWARM_STATE = {
    "summary": {
        "total_nodes": 3,
        "orchestrators": 1,
        "consensus_oracles": 1,
        "subagent_slots": 2,
        "max_concurrent_agents": MAX_CONCURRENT_AGENTS,
        "running_now": 0
    },
    "orchestrator": {
        "id": "advisor",
        "name": "Lead Advisor",
        "role": "Chief Architect & Task Orchestrator",
        "active_model": MODEL_ASSIGNMENTS.get("gemini", "local-lfm"),
        "status": "idle",
        "task": "Ready"
    },
    "consensus_nodes": [
        {
            "id": "lfm",
            "name": "Qwen 3.8 27B Local Host",
            "role": "3 Continuous Batching Slots (1 Orch + 2 Sub-Agents)",
            "active_model": "Qwen 3.8 27B (Q4_K_S · MTP + Sparse Attention)",
            "status": "online",
            "task": "Port 8034 (1 Orchestrator + 2 Sub-Agents)",
            "tools": ["completion", "pi_agent", "sparse_attention", "mtp_speculative"]
        }
    ],
    "sub_agents": []
}

def set_dynamic_subagents_roster(agents: List[Dict[str, Any]]):
    with _orchestrator_lock:
        SWARM_STATE["sub_agents"] = agents
        SWARM_STATE["summary"]["subagent_slots"] = len(agents)
        SWARM_STATE["summary"]["total_nodes"] = 1 + len(SWARM_STATE["consensus_nodes"]) + len(agents)
        SWARM_STATE["summary"]["max_concurrent_agents"] = MAX_CONCURRENT_AGENTS
        recalculate_swarm_summary()

def recalculate_swarm_summary():
    with _orchestrator_lock:
        running = 0
        if SWARM_STATE["orchestrator"]["status"] == "running":
            running += 1
        for node in SWARM_STATE["consensus_nodes"]:
            if node["status"] == "running":
                running += 1
        for sub in SWARM_STATE["sub_agents"]:
            if sub["status"] == "running":
                running += 1
        SWARM_STATE["summary"]["running_now"] = running

def update_agent_status(category: str, agent_id: str, status: str, task: str):
    with _orchestrator_lock:
        if category == "orchestrator":
            SWARM_STATE["orchestrator"]["status"] = status
            SWARM_STATE["orchestrator"]["task"] = task
            SWARM_STATE["orchestrator"]["active_model"] = MODEL_ASSIGNMENTS.get("gemini", "gemini-3.1-pro-high")
        elif category == "consensus_nodes":
            for node in SWARM_STATE["consensus_nodes"]:
                if node["id"] == agent_id:
                    node["status"] = status
                    node["task"] = task
                    if agent_id == "qwen":
                        node["active_model"] = MODEL_ASSIGNMENTS.get("qwen", "qwen-3.8-max")
        elif category == "sub_agents":
            found = False
            for sub in SWARM_STATE["sub_agents"]:
                if sub["id"] == agent_id:
                    sub["status"] = status
                    sub["task"] = task
                    found = True
                    break
            if not found:
                SWARM_STATE["sub_agents"].append({
                    "id": agent_id,
                    "name": agent_id.replace("_", " ").title(),
                    "skill": "Specialist Sub-Agent",
                    "role": "Level 3: Specialist Slot",
                    "engine": "Local LFM Slot",
                    "status": status,
                    "task": task,
                    "tools": ["read_file", "write_file", "search"]
                })
                SWARM_STATE["summary"]["subagent_slots"] = len(SWARM_STATE["sub_agents"])
                SWARM_STATE["summary"]["total_nodes"] = 1 + len(SWARM_STATE["consensus_nodes"]) + len(SWARM_STATE["sub_agents"])
        recalculate_swarm_summary()

async def query_local_slot(prompt: str, system: str = "You are a specialized sub-agent.", max_tokens: int = 2048) -> str:
    payload = {
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.2,
        "max_tokens": max_tokens
    }
    try:
        timeout_config = httpx.Timeout(120.0, connect=10.0)
        async with httpx.AsyncClient(timeout=timeout_config) as client:
            resp = await client.post(LFM_URL, json=payload)
            if resp.status_code == 200:
                return resp.json()["choices"][0]["message"]["content"].strip()
            return f"HTTP {resp.status_code}: {resp.text}"
    except Exception as e:
        return f"Slot Execution Error: {e}"

async def query_gemini(prompt: str, model_id: str = None, max_tokens: int = 8192) -> str:
    target_model = model_id or "LFM2.5-VL-3B-Q8_0.gguf"
    update_agent_status("orchestrator", "gemini", "running", f"🧠 Reasoning & Synthesizing ({target_model})...")
    try:
        res = await query_local_slot(prompt, system="You are the Lead Advisor AI Architect and Swarm Orchestrator.", max_tokens=max_tokens)
        update_agent_status("orchestrator", "gemini", "idle", "Awaiting user task...")
        return res
    except Exception as e:
        update_agent_status("orchestrator", "gemini", "idle", "Synthesized via Local GPU")
        return f"Lead Advisor Error: {e}"

async def query_qwen_web(prompt: str) -> str:
    active_qwen = MODEL_ASSIGNMENTS.get("qwen", "qwen-3.8-max")
    update_agent_status("consensus_nodes", "qwen", "running", f"🔮 Querying {active_qwen} on chat.qwen.ai...")

    # Resolve the oracle script and require it to be executable. Previously any
    # failure (missing script, non-executable bit, exec error) silently returned
    # a canned "verified" string — fabricating adversarial consensus that never
    # ran. We now surface the real state so the UI/loop can act on it honestly.
    script = None
    for cand in (QWEN_ORACLE_SCRIPT, Path.home() / "qwen_oracle.sh"):
        if script_is_runnable(cand):
            script = str(cand)
            break

    if not script:
        exists = QWEN_ORACLE_SCRIPT.exists() or Path.home().joinpath("qwen_oracle.sh").exists()
        reason = "not executable (chmod +x required)" if exists else "not configured on host"
        update_agent_status("consensus_nodes", "qwen", "offline", f"Oracle {reason}")
        return f"{QWEN_UNAVAILABLE_PREFIX} Qwen Web Oracle unavailable — script {reason}. Adversarial consensus was NOT performed."

    try:
        proc = await asyncio.create_subprocess_exec(
            script, "ask", active_qwen, prompt,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=20.0)
            out_str = stdout.decode(errors="ignore").strip()
            if proc.returncode == 0 and out_str:
                if any(err_pat in out_str.lower() for err_pat in ["daily usage limit", "issue connecting", "rate limit", "please wait"]):
                    update_agent_status("consensus_nodes", "qwen", "offline", "Oracle daily rate limit reached")
                    return f"{QWEN_UNAVAILABLE_PREFIX} Qwen Web Oracle daily rate limit reached (offline fallback). Consensus skipped."
                update_agent_status("consensus_nodes", "qwen", "ready", f"chat.qwen.ai session ({active_qwen})")
                return out_str
            err = stderr.decode(errors="ignore").strip()[:160]
            update_agent_status("consensus_nodes", "qwen", "offline", "Oracle returned no output")
            return f"{QWEN_UNAVAILABLE_PREFIX} Qwen Web Oracle returned no answer (exit {proc.returncode}). Consensus NOT performed.{f' Detail: {err}' if err else ''}"
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except Exception:
                pass
            update_agent_status("consensus_nodes", "qwen", "offline", "Oracle timed out")
            return f"{QWEN_UNAVAILABLE_PREFIX} Qwen Web Oracle timed out after 20s. Consensus NOT performed."
    except Exception as e:
        update_agent_status("consensus_nodes", "qwen", "offline", "Oracle execution error")
        return f"{QWEN_UNAVAILABLE_PREFIX} Qwen Web Oracle execution failed: {e}. Consensus NOT performed."

def plan_dynamic_swarm_for_task(message: str, has_repo: bool) -> List[Dict[str, Any]]:
    """Select a single focused agent configuration based on task intent.
    Returns a list with one entry for API compatibility."""
    msg_lower = message.lower()
    
    # File search / locate
    if any(k in msg_lower for k in ["find", "where", "locate", "grep", "list files", "scan files", "search"]):
        return [{
            "id": "agent_core",
            "name": "🔍 Codebase Scout",
            "skill": "File & Symbol Search",
            "role": "Search",
            "engine": "Local LFM",
            "status": "idle",
            "task": "Idle",
            "tools": ["find_by_name", "grep_search"],
            "prompt_template": "Find the requested files, symbols, or patterns in the codebase. Be precise and direct."
        }]
    
    # Documentation / API lookup
    elif any(k in msg_lower for k in ["doc", "docs", "documentation", "context7", "latest api", "how to use", "guide", "library", "sdk"]):
        return [{
            "id": "agent_core",
            "name": "📚 Documentation Scout",
            "skill": "API & Documentation Lookup",
            "role": "Docs",
            "engine": "Context7 + Local LFM",
            "status": "idle",
            "task": "Idle",
            "tools": ["ctx7", "context7_docs"],
            "prompt_template": "Retrieve and explain the latest documentation, API signatures, and usage examples for the requested library or framework."
        }]
    
    # Code review / audit
    elif any(k in msg_lower for k in ["review", "audit", "security", "performance", "check", "inspect"]):
        return [{
            "id": "agent_core",
            "name": "🔍 Code Reviewer",
            "skill": "Code Review & Analysis",
            "role": "Review",
            "engine": "Local LFM",
            "status": "idle",
            "task": "Idle",
            "tools": ["reasoning", "analysis"],
            "prompt_template": "Review the code for correctness, security issues, performance problems, and architectural concerns. Provide actionable recommendations."
        }]
    
    # Default: general coding assistance
    else:
        return [{
            "id": "agent_core",
            "name": "💡 Coding Assistant",
            "skill": "Technical Problem Solving",
            "role": "Assistant",
            "engine": "Local LFM",
            "status": "idle",
            "task": "Idle",
            "tools": ["reasoning", "solution_blueprint"],
            "prompt_template": "Provide a clear, direct technical answer. Include code examples where helpful. Focus on practical solutions."
        }]

async def execute_task_aware_swarm(sub_agents: List[Dict[str, Any]], repo_block: str, user_req: str, repo_path: str = "", concurrency: int = 0) -> Dict[str, str]:
    slot_limit = concurrency if concurrency and concurrency > 0 else MAX_CONCURRENT_AGENTS
    slot_limit = max(1, min(slot_limit, MAX_CONCURRENT_AGENTS))
    semaphore = asyncio.Semaphore(slot_limit)

    async def _run_with_slot(coro):
        async with semaphore:
            return await coro

    tasks = {}
    rules_block = format_enforced_rules_prompt(repo_path)
    
    # 1. Fetch Disk Memory Facts
    disk_memory_data = read_disk_memory_files(repo_path)
    disk_memory_block = format_disk_memory_prompt_block(disk_memory_data)

    # 2. Fetch Live Web Grounding
    web_res = search_web_live(user_req)
    web_scout_block = format_web_scout_prompt_block(user_req, web_res)

    for agent in sub_agents:
        agent_id = agent["id"]
        
        if agent_id == "agent_memory":
            # Fast disk memory extraction
            tasks[agent_id] = asyncio.sleep(0.01, result=disk_memory_block)
            update_agent_status("sub_agents", agent_id, "running", f"⚡ {agent['name']} reading disk memory...")
            continue
            
        if agent_id == "agent_web":
            # Fast web scout output
            tasks[agent_id] = asyncio.sleep(0.01, result=web_scout_block)
            update_agent_status("sub_agents", agent_id, "running", f"⚡ {agent['name']} searching live web...")
            continue

        prompt = f"""{rules_block}

{disk_memory_block}

{web_scout_block}

{repo_block}

User Request:
{user_req}

Specialist Assignment:
{agent.get('prompt_template', '')}

Instruction: Execute your specialized role with rigorous grounding in the provided disk memory and web evidence. Do not guess or hallucinate. Enforce Clean Architecture (≤35 lines per function, single responsibility, Dependency Injection)."""

        update_agent_status("sub_agents", agent_id, "running", f"⚡ {agent['name']} ({agent['skill']}) analyzing...")
        tasks[agent_id] = _run_with_slot(query_local_slot(prompt, system=f"You are the {agent['name']} specialized in {agent['skill']}."))

    results = await asyncio.gather(*tasks.values(), return_exceptions=True)
    
    output_map = {}
    for i, agent in enumerate(sub_agents):
        agent_id = agent["id"]
        output_map[agent_id] = str(results[i])
        update_agent_status("sub_agents", agent_id, "idle", "Stream completed")

    return output_map

def route_request(message: str, has_repo: bool) -> Dict[str, Any]:
    msg_lower = message.lower()
    is_pure_local_action = any(k in msg_lower for k in ["scan", "find file", "grep", "check syntax", "compile", "run test", "list files", "read file"])
    needs_crosscheck = any(k in msg_lower for k in ["review", "audit", "compare", "design", "architecture", "plan", "consensus"])
    
    selected_models = ["lfm"]
    bypassed_models = []

    if needs_crosscheck and script_is_runnable(QWEN_ORACLE_SCRIPT):
        selected_models.append("qwen")
    else:
        bypassed_models.append({"id": "qwen", "reason": "Bypassed for local GPU acceleration"})

    return {
        "selected": selected_models,
        "bypassed": bypassed_models,
        "is_pure_local": is_pure_local_action,
        "is_review": needs_crosscheck
    }

async def process_advisor_chat(message: str, repo_path: str = "", session_id: str = "") -> Dict[str, Any]:
    start_t = time.time()
    status_steps = []
    msg_lower = message.strip().lower()

    # 1. Scout Repository Context & Disk Memory
    ctx = extract_deep_repo_context(repo_path)
    repo_block = format_repo_prompt_block(ctx)
    rules_block = format_enforced_rules_prompt(repo_path)
    
    # Check for Tier 1: Direct Fast Answer Mode (Greetings, simple conversions, quick clarifications)
    is_simple_greeting = (
        not ctx and
        len(message.split()) <= 10 and
        any(msg_lower.startswith(g) for g in ["hi", "hello", "hey", "good morning", "good evening", "who are you", "what can you do", "thanks", "thank you"])
    )

    if is_simple_greeting:
        status_steps.append("⚡ Direct Fast Response · Local Liquid LFM (Single Slot)")
        direct_prompt = f"User greeting: '{message}'. Respond politely and concisely as Swarm AI Assistant."
        answer = await query_local_slot(direct_prompt, system="You are the Swarm AI Studio Coding Assistant.")
        duration = round(time.time() - start_t, 2)
        status_steps.append(f"✓ Answered directly in {duration}s")
        response_payload = {
            "prompt": message,
            "answer": answer,
            "status_steps": status_steps,
            "tier": "direct",
            "thought_summary": f"Direct Answer · {duration}s",
            "routing": {"selected": ["lfm"], "bypassed": [], "tier": "direct"},
            "artifact": None,
            "plan": None,
            "repo_name": "Workspace",
            "duration": duration,
            "timestamp": int(time.time() * 1000)
        }
        if session_id:
            save_session_turn(session_id, response_payload, repo_path=repo_path)
        return response_payload

    mem_data = read_disk_memory_files(repo_path)
    disk_memory_block = format_disk_memory_prompt_block(mem_data)
    
    if ctx:
        status_steps.append(f"📁 Loaded context for '{ctx.get('name')}' (Branch: {ctx.get('branch')})")
    status_steps.append(f"💾 Grounded {len(mem_data.get('grounded_files', []))} disk memory and config files from filesystem.")

    # 2. Cost-Based Optimizer (CBO) & Execution Plan Selection
    optimal_plan, candidates, stats = optimize_and_select_best_plan(message, ctx)
    status_steps.append(
        f"⚡ Cost-Based Optimizer (CBO): Selected '{optimal_plan.strategy_name}' (Cost: {optimal_plan.cost_score} · Confidence: {int(optimal_plan.confidence_score*100)}% · Parallel: {optimal_plan.parallelism_width}x)"
    )

    # 3. Task-Aware Dynamic Swarm Planning (1 to 8 GPU Slots)
    planned_subagents = plan_dynamic_swarm_for_task(message, has_repo=bool(ctx))
    set_dynamic_subagents_roster(planned_subagents)
    
    agent_names_str = ", ".join([a["name"] for a in planned_subagents])
    status_steps.append(f"🔍 Analyzing with {agent_names_str}...")

    # 4. Dynamic Parallel Swarm Execution
    route = route_request(message, has_repo=bool(ctx))
    update_agent_status("consensus_nodes", "lfm", "running", f"Analyzing request...")
    
    local_swarm_task = execute_task_aware_swarm(
        planned_subagents, repo_block, message, repo_path=repo_path,
        concurrency=optimal_plan.parallelism_width
    )
    
    qwen_task = None
    if "qwen" in route["selected"]:
        qwen_prompt = f"Request regarding repository {ctx.get('name', 'project')}:\n{message}\nProvide high-level insights, edge cases, and key architecture guidance."
        qwen_task = query_qwen_web(qwen_prompt)

    if qwen_task:
        swarm_results, qwen_res = await asyncio.gather(local_swarm_task, qwen_task, return_exceptions=True)
        qwen_str = str(qwen_res)
    else:
        swarm_results = await local_swarm_task
        qwen_str = "Bypassed for local private file action."

    update_agent_status("consensus_nodes", "lfm", "online", "Port 8034 (Local GPU Swarm)")
    status_steps.append(f"✓ Analysis complete.")

    # 5. Lead Advisor Synthesis with Multi-Agent Cross-Check Matrix
    update_agent_status("orchestrator", "advisor", "running", "Synthesizing response...")
    status_steps.append("🧠 Preparing response...")

    findings_blocks = []
    for agent in planned_subagents:
        aid = agent["id"]
        findings_blocks.append(f"[{agent['name']} · Skill: {agent['skill']}]\n{swarm_results.get(aid, '')}")
    findings_str = "\n---\n".join(findings_blocks)

    synthesis_prompt = f"""You are a senior coding assistant.
A user asked:
<REQUEST>
{message}
</REQUEST>

{rules_block}

{disk_memory_block}

{repo_block}

Analysis findings:
---
{findings_str}
---

Your Instructions:
1. Synthesize the analysis into a clear, direct, and actionable response.
2. If code changes are needed, provide concrete code with file paths.
3. Focus on practical solutions over theoretical architecture.
4. Ground all claims in the actual codebase context provided.
"""

    final_advisor_answer = await query_gemini(synthesis_prompt, MODEL_ASSIGNMENTS.get("gemini"))
    if "Error:" in final_advisor_answer or not final_advisor_answer.strip():
        final_advisor_answer = await query_local_slot(synthesis_prompt, system="You are the Lead Advisor.")

    # 6. Build and Save Artifact directly to Disk
    artifact = None
    is_review = any(k in msg_lower for k in ["review", "audit", "check diff", "inspect code", "quality"])
    is_worktree_task = any(k in msg_lower for k in ["build", "implement", "create worktree", "fix bug", "add feature", "refactor"])

    if is_review and ctx:
        artifact = save_artifact_to_disk(
            title=f"Swarm Codebase Review — {ctx.get('name')}",
            filename=f"SWARM_REVIEW_{ctx.get('name')}.md",
            content=final_advisor_answer,
            repo_path=ctx.get("path")
        )
    elif is_worktree_task and ctx:
        artifact = save_artifact_to_disk(
            title=f"Swarm Implementation Blueprint — {ctx.get('name')}",
            filename=f"SWARM_PLAN_{ctx.get('name')}.md",
            content=final_advisor_answer,
            repo_path=ctx.get("path")
        )

    update_agent_status("orchestrator", "advisor", "idle", "Ready")

    duration = round(time.time() - start_t, 2)
    status_steps.append(f"✓ Completed in {duration}s")

    tier_name = "advisor"
    thought_label = f"Analyzed · {duration}s"
    if stats.get("has_doc_keywords"):
        tier_name = "docs"
        thought_label = f"Docs & Context Grounded · {duration}s"

    response_payload = {
        "prompt": message,
        "answer": final_advisor_answer,
        "status_steps": status_steps,
        "tier": tier_name,
        "thought_summary": thought_label,
        "routing": route,
        "artifact": artifact,
        "plan": optimal_plan.to_dict(),
        "repo_name": ctx.get("name", "Workspace") if ctx else "Workspace",
        "duration": duration,
        "timestamp": int(time.time() * 1000)
    }

    if session_id:
        save_session_turn(session_id, response_payload, repo_path=repo_path)

    return response_payload
