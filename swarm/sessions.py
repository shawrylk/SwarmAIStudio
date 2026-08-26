"""
Multi-Chat Session Persistence Engine (~/.swarm/sessions/)
Features atomic checkpoint writes (atomic_write_json) and auto-detection of interrupted runs on restart.
"""

import os
import json
import time
import re
import uuid
from pathlib import Path
from typing import List, Dict, Any, Optional
from swarm.config import SESSIONS_DIR, LOOP_SESSIONS_DIR
from swarm.logger import log_event

def atomic_write_json(file_path: Path, data: Any):
    """
    Crash-resilient atomic file write using temp file + atomic rename (replace).
    Guarantees no partial or corrupt JSON files even on SIGKILL / crash mid-write.
    """
    file_path.parent.mkdir(parents=True, exist_ok=True)
    temp_file = file_path.with_suffix(f".tmp.{os.getpid()}.{uuid.uuid4().hex[:6]}")
    try:
        content = json.dumps(data, indent=2)
        temp_file.write_text(content, encoding="utf-8")
        temp_file.replace(file_path)
    except Exception:
        if temp_file.exists():
            try:
                temp_file.unlink()
            except Exception:
                pass
        raise

def get_session_file(session_id: str) -> Path:
    safe_id = re.sub(r"[^a-zA-Z0-9_-]", "_", session_id)
    return SESSIONS_DIR / f"{safe_id}.json"

def list_sessions() -> List[Dict[str, Any]]:
    sessions = []
    for f in SESSIONS_DIR.glob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            sessions.append({
                "id": data.get("id", f.stem),
                "title": data.get("title", "Untitled Chat"),
                "created_at": data.get("created_at", int(time.time() * 1000)),
                "updated_at": data.get("updated_at", int(time.time() * 1000)),
                "message_count": len(data.get("messages", [])),
                "repo_path": data.get("repo_path", ""),
                "linked_loop_sessions": data.get("linked_loop_sessions", []),
                "last_loop_session_id": data.get("last_loop_session_id", "")
            })
        except Exception:
            pass
    sessions.sort(key=lambda s: s["updated_at"], reverse=True)
    if not sessions:
        new_sess = create_new_session("Main Advisory Thread")
        sessions.append(new_sess)
    return sessions

def create_new_session(title: str = "New Chat", repo_path: str = "") -> Dict[str, Any]:
    sess_id = f"sess_{int(time.time())}_{uuid.uuid4().hex[:6]}"
    now = int(time.time() * 1000)
    session_data = {
        "id": sess_id,
        "title": title,
        "created_at": now,
        "updated_at": now,
        "repo_path": repo_path,
        "messages": [],
        "linked_loop_sessions": [],
        "last_loop_session_id": ""
    }
    atomic_write_json(get_session_file(sess_id), session_data)
    return {
        "id": sess_id,
        "title": title,
        "created_at": now,
        "updated_at": now,
        "message_count": 0,
        "repo_path": repo_path,
        "linked_loop_sessions": [],
        "last_loop_session_id": ""
    }

def load_session(session_id: str) -> Optional[Dict[str, Any]]:
    f = get_session_file(session_id)
    if f.exists():
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            pass
    all_sess = list_sessions()
    if all_sess:
        fallback_file = get_session_file(all_sess[0]["id"])
        if fallback_file.exists():
            return json.loads(fallback_file.read_text(encoding="utf-8"))
    return create_new_session("Main Advisory Thread")

def save_session_turn(session_id: str, turn_data: Dict[str, Any], repo_path: str = ""):
    session = load_session(session_id)
    if not session:
        session = {
            "id": session_id,
            "title": turn_data.get("prompt", "New Chat")[:32],
            "created_at": int(time.time() * 1000),
            "updated_at": int(time.time() * 1000),
            "repo_path": repo_path,
            "messages": [],
            "linked_loop_sessions": [],
            "last_loop_session_id": ""
        }
    if session.get("title") == "New Chat" and turn_data.get("prompt"):
        session["title"] = turn_data["prompt"][:35] + ("..." if len(turn_data["prompt"]) > 35 else "")
    
    session["updated_at"] = int(time.time() * 1000)
    if repo_path:
        session["repo_path"] = repo_path
    session["messages"].append(turn_data)
    atomic_write_json(get_session_file(session["id"]), session)

def delete_session(session_id: str):
    f = get_session_file(session_id)
    if f.exists():
        try:
            f.unlink()
        except Exception:
            pass

def rename_session(session_id: str, new_title: str):
    session = load_session(session_id)
    if session:
        session["title"] = new_title.strip() or "Untitled Chat"
        session["updated_at"] = int(time.time() * 1000)
        atomic_write_json(get_session_file(session_id), session)


# ─────────────────────────────────────────────────────────────
# Auto-Dev Loop Session Persistence (~/.swarm/loop_sessions/)
# ─────────────────────────────────────────────────────────────

def get_loop_session_file(session_id: str) -> Path:
    safe_id = re.sub(r"[^a-zA-Z0-9_-]", "_", session_id)
    return LOOP_SESSIONS_DIR / f"{safe_id}.json"

def detect_and_recover_interrupted_sessions() -> List[Dict[str, Any]]:
    """
    Inspects ~/.swarm/loop_sessions/ on startup for any sessions where status == 'running'.
    Marks status as 'interrupted' with an explicit timestamp and live_log entry noting the server was restarted.
    Cleans up any orphaned temporary write files (.tmp.*).
    """
    interrupted_sessions = []
    
    # Clean up any orphaned temporary files from sudden crash
    for tmp_f in list(LOOP_SESSIONS_DIR.glob("*.tmp.*")) + list(SESSIONS_DIR.glob("*.tmp.*")):
        try:
            tmp_f.unlink()
        except Exception:
            pass

    for f in LOOP_SESSIONS_DIR.glob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            if data.get("status") in ("running", "recovering"):
                sess_id = data.get("session_id") or data.get("id") or f.stem
                data["status"] = "interrupted"
                data["interrupted_at"] = int(time.time() * 1000)
                data["updated_at"] = int(time.time() * 1000)
                
                timestamp = time.strftime('%H:%M:%S', time.localtime())
                recovery_log = {
                    "timestamp": timestamp,
                    "message": "⚠️ Server was restarted or terminated during execution. Session marked as interrupted (checkpoint preserved for resume).",
                    "category": "system",
                    "is_active": False
                }
                data.setdefault("live_logs", []).append(recovery_log)
                save_loop_session(data)
                interrupted_sessions.append(data)
                log_event("warn", "recovery", f"Detected interrupted loop session '{sess_id}'. Marked as interrupted/recoverable.")
        except Exception:
            pass

    return interrupted_sessions

def list_loop_sessions() -> List[Dict[str, Any]]:
    sessions = []
    for f in LOOP_SESSIONS_DIR.glob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            sess_id = data.get("session_id") or data.get("id") or f.stem
            title = data.get("title") or data.get("name") or "Untitled Loop Run"
            sessions.append({
                "id": sess_id,
                "session_id": sess_id,
                "name": title,
                "title": title,
                "goal": data.get("goal", ""),
                "status": data.get("status", "idle"),
                "created_at": data.get("created_at", int(time.time() * 1000)),
                "updated_at": data.get("updated_at", int(time.time() * 1000)),
                "interrupted_at": data.get("interrupted_at", 0),
                "tasks_count": len(data.get("tasks", [])),
                "current_task_id": data.get("current_task_id"),
                "repo_path": data.get("repo_path", ""),
                "advisor_session_id": data.get("advisor_session_id", ""),
                "has_github_issue": bool(data.get("github_issue")),
                "has_certificate": bool(data.get("verification_certificate"))
            })
        except Exception:
            pass
    sessions.sort(key=lambda s: s["updated_at"], reverse=True)
    if not sessions:
        new_sess = create_new_loop_session("Main Auto-Dev Loop")
        sessions.append(new_sess)
    return sessions

def create_new_loop_session(title: str = "New Auto-Dev Loop", goal: str = "", repo_path: str = "", advisor_session_id: str = "") -> Dict[str, Any]:
    sess_id = f"loop_{int(time.time())}_{uuid.uuid4().hex[:6]}"
    now = int(time.time() * 1000)
    clean_title = title.strip() or (goal[:35] + ("..." if len(goal) > 35 else "")) or "New Auto-Dev Loop"
    session_data = {
        "id": sess_id,
        "session_id": sess_id,
        "name": clean_title,
        "title": clean_title,
        "goal": goal.strip(),
        "repo_path": repo_path,
        "created_at": now,
        "updated_at": now,
        "status": "idle",
        "research_brief": "",
        "tasks": [],
        "current_task_id": None,
        "attempts": 0,
        "live_logs": [],
        "advisor_pings": [],
        "github_issue": None,
        "verification_certificate": "",
        "advisor_session_id": advisor_session_id,
        "iteration": 0,
        "max_iterations": 20,
        "active_subagent": None,
        "started_at": 0,
        "completed_at": 0,
        "final_summary": ""
    }
    atomic_write_json(get_loop_session_file(sess_id), session_data)
    return {
        "id": sess_id,
        "session_id": sess_id,
        "name": clean_title,
        "title": clean_title,
        "goal": goal.strip(),
        "repo_path": repo_path,
        "created_at": now,
        "updated_at": now,
        "status": "idle",
        "tasks_count": 0,
        "current_task_id": None,
        "advisor_session_id": advisor_session_id,
        "has_github_issue": False,
        "has_certificate": False
    }

def load_loop_session(session_id: str) -> Optional[Dict[str, Any]]:
    f = get_loop_session_file(session_id)
    if f.exists():
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            if "session_id" not in data and "id" in data:
                data["session_id"] = data["id"]
            if "id" not in data and "session_id" in data:
                data["id"] = data["session_id"]
            if "title" not in data and "name" in data:
                data["title"] = data["name"]
            if "name" not in data and "title" in data:
                data["name"] = data["title"]
            return data
        except Exception:
            pass
    return None

def save_loop_session(session_data: Dict[str, Any]):
    sess_id = session_data.get("session_id") or session_data.get("id")
    if not sess_id:
        return
    session_data["id"] = sess_id
    session_data["session_id"] = sess_id
    if "title" not in session_data and "name" in session_data:
        session_data["title"] = session_data["name"]
    if "name" not in session_data and "title" in session_data:
        session_data["name"] = session_data["title"]
    session_data["updated_at"] = int(time.time() * 1000)
    atomic_write_json(get_loop_session_file(sess_id), session_data)

def delete_loop_session(session_id: str):
    f = get_loop_session_file(session_id)
    if f.exists():
        try:
            f.unlink()
        except Exception:
            pass

def rename_loop_session(session_id: str, new_title: str):
    session = load_loop_session(session_id)
    if session:
        t = new_title.strip() or "Untitled Loop Run"
        session["title"] = t
        session["name"] = t
        save_loop_session(session)

def link_advisor_and_loop_sessions(advisor_session_id: str, loop_session_id: str):
    if advisor_session_id:
        adv = load_session(advisor_session_id)
        if adv:
            linked = adv.setdefault("linked_loop_sessions", [])
            if loop_session_id not in linked:
                linked.append(loop_session_id)
            adv["last_loop_session_id"] = loop_session_id
            adv["loop_session_id"] = loop_session_id
            atomic_write_json(get_session_file(adv["id"]), adv)
    if loop_session_id:
        loop_sess = load_loop_session(loop_session_id)
        if loop_sess:
            loop_sess["advisor_session_id"] = advisor_session_id
            save_loop_session(loop_sess)
