"""
Super-Orchestrator Multi-Engine Execution Bridge
Unifies and bridges all installed local and cloud AI engines:
1. Claude Code CLI (`claude -p`) — Deep reasoning & escalation engine
2. Antigravity / Gemini CLI (`agy` / `gemini`) — Codebase orchestration engine
3. Context7 MCP CLI (`ctx7`) — Real-time 2026 documentation extraction
4. Local Liquid LFM 2.5 — Zero-cost continuous batching GPU slots (Port 8034)
5. Qwen 3.8 Max Web Oracle — Adversarial consensus peer
"""

import os
import shutil
import asyncio
import subprocess
import time
from pathlib import Path
from typing import Dict, Any, List, Optional
import httpx

from swarm.config import LFM_URL, LFM_HEALTH_URL, QWEN_ORACLE_SCRIPT
from swarm.logger import log_event

CLAUDE_BIN = shutil.which("claude") or str(Path.home() / ".local" / "bin" / "claude")
AGY_BIN = shutil.which("agy") or str(Path.home() / ".local" / "bin" / "agy")
GEMINI_BIN = shutil.which("gemini") or str(Path.home() / ".nvm" / "versions" / "node" / "v24.15.0" / "bin" / "gemini")
CTX7_BIN = shutil.which("ctx7") or str(Path.home() / ".nvm" / "versions" / "node" / "v24.15.0" / "bin" / "ctx7")

def get_cli_version(bin_path: str, flag: str = "--version") -> Optional[str]:
    try:
        if not bin_path or not Path(bin_path).exists():
            return None
        res = subprocess.run([bin_path, flag], capture_output=True, text=True, timeout=2.5)
        if res.returncode == 0:
            return res.stdout.strip().splitlines()[0] if res.stdout.strip() else "Available"
    except Exception:
        pass
    return None

async def check_lfm_health() -> Dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=1.5) as client:
            res = await client.get(LFM_HEALTH_URL)
            if res.status_code == 200:
                return {"available": True, "status": "online", "details": "8 Continuous Batching Slots"}
    except Exception:
        pass
    return {"available": False, "status": "offline", "details": "Port 8034 unreachable"}

async def probe_all_backends() -> Dict[str, Any]:
    """Probes and returns the availability status of all 5 execution backends."""
    claude_v = get_cli_version(CLAUDE_BIN)
    agy_v = get_cli_version(AGY_BIN)
    gemini_v = get_cli_version(GEMINI_BIN)
    ctx7_v = get_cli_version(CTX7_BIN)
    lfm_status = await check_lfm_health()
    qwen_avail = Path(QWEN_ORACLE_SCRIPT).exists() or Path.home().joinpath("qwen_oracle.sh").exists()

    backends = {
        "claude_code": {
            "id": "claude_code",
            "name": "Claude Code CLI",
            "role": "Deep Reasoning & Escalation Engine",
            "type": "cli",
            "bin": CLAUDE_BIN,
            "version": claude_v or "Not detected",
            "available": bool(claude_v),
            "status": "ready" if claude_v else "unavailable",
            "capabilities": ["deep_refactor", "complex_logic", "escalation_of_last_resort"]
        },
        "agy_gemini": {
            "id": "agy_gemini",
            "name": "Antigravity (AGY) & Gemini Engine",
            "role": "Lead Architect & Codebase Orchestrator",
            "type": "cli_and_cloud",
            "bin": AGY_BIN if Path(AGY_BIN).exists() else GEMINI_BIN,
            # Honest availability: a CLI must actually be detected. When neither
            # agy nor gemini is present the orchestrator falls back to the local
            # GPU model, so we report that degraded state instead of a fake "ready".
            "version": agy_v or gemini_v or "Local GPU fallback (LFM 2.5)",
            "available": bool(agy_v or gemini_v),
            "status": "ready" if (agy_v or gemini_v) else "fallback_local",
            "capabilities": ["full_repo_orchestration", "multi_stage_synthesis", "cbo_optimization"]
        },
        "context7_mcp": {
            "id": "context7_mcp",
            "name": "Context7 Documentation MCP",
            "role": "Real-time 2026 API & Doc Scout",
            "type": "mcp_and_cli",
            "bin": CTX7_BIN,
            "version": ctx7_v or "Context7 MCP 0.5.8",
            "available": bool(ctx7_v),
            "status": "ready" if ctx7_v else "fallback_local",
            "capabilities": ["live_api_lookup", "2026_framework_grounding", "zero_hallucination_signatures"]
        },
        "liquid_lfm": {
            "id": "liquid_lfm",
            "name": "Liquid LFM 2.5 (Local GPU Host)",
            "role": "Continuous Batching Sub-Agent Slots",
            "type": "local_gpu",
            "bin": "http://localhost:8034",
            "version": "Liquid LFM 2.5 (2.6B Q8)",
            "available": lfm_status["available"],
            "status": lfm_status["status"],
            "capabilities": ["zero_cost_ast_scans", "rapid_syntax_checks", "parallel_file_routing"]
        },
        "qwen_oracle": {
            "id": "qwen_oracle",
            "name": "Qwen 3.8 Max Web Oracle",
            "role": "Adversarial Consensus & Hallucination Gatekeeper",
            "type": "web_and_cli",
            "bin": str(QWEN_ORACLE_SCRIPT),
            "version": "Qwen 3.8 Max",
            "available": qwen_avail,
            "status": "ready" if qwen_avail else "simulated",
            "capabilities": ["adversarial_review", "security_threat_audit", "peer_consensus"]
        }
    }

    active_count = sum(1 for b in backends.values() if b["available"] or b["status"] == "ready")
    
    return {
        "backends": backends,
        "total_count": len(backends),
        "active_count": active_count,
        "mode": "Unified Super-Orchestrator"
    }

async def execute_claude_cli(prompt: str, cwd: str = "", timeout_secs: int = 45) -> str:
    """Executes a prompt through Claude Code CLI (`claude -p`)."""
    if not CLAUDE_BIN or not Path(CLAUDE_BIN).exists():
        return "Claude CLI binary not found on host."

    work_dir = cwd if (cwd and Path(cwd).exists()) else str(Path.home())
    log_event("info", "bridge", f"Executing Claude CLI prompt in {work_dir}", {"prompt_len": len(prompt)})

    try:
        proc = await asyncio.create_subprocess_exec(
            CLAUDE_BIN,
            "-p", prompt,
            cwd=work_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_secs)
        out_str = stdout.decode("utf-8", errors="ignore").strip()
        err_str = stderr.decode("utf-8", errors="ignore").strip()

        if proc.returncode == 0 and out_str:
            log_event("info", "bridge", f"Claude CLI responded successfully ({len(out_str)} chars)")
            return out_str
        elif err_str:
            log_event("warn", "bridge", f"Claude CLI returned stderr: {err_str[:120]}")
            return f"Claude CLI notice: {out_str or err_str}"
        return out_str or "No output from Claude CLI."
    except asyncio.TimeoutError:
        log_event("error", "bridge", f"Claude CLI timed out after {timeout_secs}s")
        return f"Claude CLI query timed out after {timeout_secs}s."
    except Exception as e:
        log_event("error", "bridge", f"Claude CLI execution error: {e}")
        return f"Claude CLI execution failed: {e}"

async def execute_context7_cli(library: str, query: str) -> str:
    """Queries live documentation through Context7 CLI (`ctx7 doc`)."""
    from swarm.context7_engine import fetch_latest_doc_context
    return fetch_latest_doc_context(library, query)

async def test_backend_connection(backend_id: str, sample_prompt: str = "Explain Dependency Injection in 1 sentence") -> Dict[str, Any]:
    """Runs a quick live diagnostic ping on any selected backend engine."""
    start_t = time.time()
    
    if backend_id == "claude_code":
        out = await execute_claude_cli(sample_prompt, timeout_secs=15)
        duration = round(time.time() - start_t, 2)
        return {"backend": "claude_code", "success": "failed" not in out.lower(), "duration_s": duration, "response": out[:200]}

    elif backend_id == "context7_mcp":
        from swarm.context7_engine import query_context7_docs
        out = query_context7_docs("fastapi", "router")
        duration = round(time.time() - start_t, 2)
        out_text = (out.get("content", "") if isinstance(out, dict) else str(out)) if out else "No docs"
        return {"backend": "context7_mcp", "success": bool(out), "duration_s": duration, "response": out_text[:200]}

    elif backend_id == "liquid_lfm":
        from swarm.orchestrator import query_local_slot
        out = await query_local_slot(sample_prompt)
        duration = round(time.time() - start_t, 2)
        return {"backend": "liquid_lfm", "success": bool(out), "duration_s": duration, "response": out[:200]}

    elif backend_id == "qwen_oracle":
        from swarm.orchestrator import query_qwen_web
        out = await query_qwen_web(sample_prompt)
        duration = round(time.time() - start_t, 2)
        return {"backend": "qwen_oracle", "success": bool(out), "duration_s": duration, "response": out[:200]}

    elif backend_id == "agy_gemini":
        from swarm.orchestrator import query_gemini
        out = await query_gemini(sample_prompt)
        duration = round(time.time() - start_t, 2)
        return {"backend": "agy_gemini", "success": "Error:" not in out, "duration_s": duration, "response": out[:200]}

    return {"backend": backend_id, "success": False, "error": "Unknown backend"}
