"""
Context7 Documentation & Live Knowledge Engine for Swarm AI Studio
Provides live, version-accurate documentation retrieval using Context7 MCP / CLI (ctx7).
Allows sub-agents and Lead Advisor to verify latest library APIs and syntax.
"""

import subprocess
import time
from typing import List, Dict, Any, Optional
from swarm.logger import log_event

def query_context7_library(library_name: str, query: str = "") -> Dict[str, Any]:
    """Resolves library name to Context7-compatible library ID."""
    t0 = time.time()
    cmd = ["ctx7", "library", library_name]
    if query:
        cmd.append(query)

    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        dur = round((time.time() - t0) * 1000, 1)
        
        if res.returncode == 0:
            log_event("info", "context7", f"Resolved library '{library_name}' ({dur}ms)")
            return {
                "success": True,
                "output": res.stdout.strip(),
                "duration_ms": dur
            }
        else:
            log_event("warn", "context7", f"Context7 library resolve failed: {res.stderr.strip()}")
            return {
                "success": False,
                "error": res.stderr.strip() or "Failed to resolve library",
                "output": res.stdout.strip(),
                "duration_ms": dur
            }
    except Exception as e:
        log_event("error", "context7", f"Exception querying Context7 library: {e}")
        return {"success": False, "error": str(e)}

def query_context7_docs(library_id: str, query: str) -> Dict[str, Any]:
    """Fetches live, version-accurate documentation for a specific library ID."""
    t0 = time.time()
    cmd = ["ctx7", "docs", library_id, query]

    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=25)
        dur = round((time.time() - t0) * 1000, 1)
        
        if res.returncode == 0:
            log_event("info", "context7", f"Fetched docs for '{library_id}' ({dur}ms)")
            return {
                "success": True,
                "library_id": library_id,
                "docs": res.stdout.strip(),
                "duration_ms": dur
            }
        else:
            log_event("warn", "context7", f"Context7 docs fetch failed: {res.stderr.strip()}")
            return {
                "success": False,
                "error": res.stderr.strip() or "Failed to fetch docs",
                "output": res.stdout.strip(),
                "duration_ms": dur
            }
    except Exception as e:
        log_event("error", "context7", f"Exception fetching Context7 docs: {e}")
        return {"success": False, "error": str(e)}

def fetch_latest_doc_context(library_or_package: str, question_or_topic: str) -> str:
    """
    Automated pipeline for sub-agents:
    Resolves library -> pulls relevant documentation markdown context.
    """
    clean_lib = library_or_package.strip().lower()
    res = query_context7_library(clean_lib, question_or_topic)
    
    if not res.get("success") or not res.get("output"):
        return f"[Context7] No live documentation found for {library_or_package}."

    output_lines = res["output"].split("\n")
    target_lib_id = ""
    for line in output_lines:
        if "Context7-compatible library ID:" in line:
            target_lib_id = line.split("Context7-compatible library ID:")[1].strip()
            break

    if target_lib_id:
        docs_res = query_context7_docs(target_lib_id, question_or_topic)
        if docs_res.get("success") and docs_res.get("docs"):
            return f"=== CONTEXT7 LATEST DOCS ({target_lib_id}) ===\n{docs_res['docs'][:4000]}\n=========================================="

    return f"=== CONTEXT7 CANDIDATE LIBRARIES ({library_or_package}) ===\n{res['output'][:2000]}\n=========================================="
