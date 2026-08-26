"""
Multi-Chat Session Persistence Engine (~/.swarm/sessions/)
"""

import json
import time
import re
import uuid
from pathlib import Path
from typing import List, Dict, Any, Optional
from swarm.config import SESSIONS_DIR

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
                "repo_path": data.get("repo_path", "")
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
        "messages": []
    }
    get_session_file(sess_id).write_text(json.dumps(session_data, indent=2), encoding="utf-8")
    return {
        "id": sess_id,
        "title": title,
        "created_at": now,
        "updated_at": now,
        "message_count": 0,
        "repo_path": repo_path
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
            "messages": []
        }
    if session.get("title") == "New Chat" and turn_data.get("prompt"):
        session["title"] = turn_data["prompt"][:35] + ("..." if len(turn_data["prompt"]) > 35 else "")
    
    session["updated_at"] = int(time.time() * 1000)
    if repo_path:
        session["repo_path"] = repo_path
    session["messages"].append(turn_data)
    get_session_file(session["id"]).write_text(json.dumps(session, indent=2), encoding="utf-8")

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
        get_session_file(session_id).write_text(json.dumps(session, indent=2), encoding="utf-8")
