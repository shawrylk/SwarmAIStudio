"""
Swarm AI Studio HTTP Server & API Dispatcher
Serves frontend assets from web/ and dispatches JSON API routes with live debug logging.
"""

import json
import asyncio
import subprocess
import time
from pathlib import Path
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, unquote
from typing import List
import httpx

from swarm.config import PORT, HOST, WEB_DIR, LFM_HEALTH_URL
from swarm.logger import log_event, get_live_logs
from swarm.telemetry import get_hardware_metrics
from swarm.git_engine import (
    find_git_repos,
    get_full_github_desktop_state,
    get_file_diff,
    get_commit_diff,
    switch_or_create_branch,
    list_worktrees,
    add_worktree,
    remove_worktree,
    list_stashes,
    save_stash,
    pop_stash,
    apply_stash,
    drop_stash,
    stash_and_switch_branch,
    run_git,
    extract_deep_repo_context
)
from swarm.sessions import (
    list_sessions,
    create_new_session,
    load_session,
    delete_session,
    rename_session
)
from swarm.artifacts import scan_all_artifacts
from swarm.model_scout import (
    scout_all_models,
    load_model_assignments,
    save_model_assignments
)
from swarm.orchestrator import SWARM_STATE, process_advisor_chat
from swarm.loop_engine import (
    get_loop_state,
    start_loop,
    pause_loop,
    resume_loop,
    stop_loop,
    ping_lead_advisor
)
from swarm.context7_engine import query_context7_library, query_context7_docs, fetch_latest_doc_context
from swarm.planner_cbo import optimize_and_select_best_plan, execute_plan_dag
from swarm.skills_scanner import scan_all_installed_skills
from swarm.rules_engine import get_global_rules, save_global_rules, discover_project_rules
from swarm.engine_bridge import probe_all_backends, test_backend_connection

MODEL_ASSIGNMENTS = load_model_assignments()

class SwarmHandler(BaseHTTPRequestHandler):
    def _send_json(self, data, status=200):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS, HEAD')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def _serve_file(self, file_path: Path, content_type: str):
        if file_path.exists() and file_path.is_file():
            self.send_response(200)
            self.send_header('Content-Type', content_type)
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate')
            self.end_headers()
            self.wfile.write(file_path.read_bytes())
        else:
            log_event("warn", "server", f"404 File Not Found: {file_path.name}")
            self.send_error(404, f"File not found: {file_path.name}")

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS, HEAD')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_HEAD(self):
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)

        # 1. Static Web Assets
        if parsed.path == '/' or parsed.path == '/index.html':
            self._serve_file(WEB_DIR / "index.html", "text/html; charset=utf-8")
        elif parsed.path == '/css/style.css':
            self._serve_file(WEB_DIR / "css" / "style.css", "text/css; charset=utf-8")
        elif parsed.path == '/js/app.js':
            self._serve_file(WEB_DIR / "js" / "app.js", "application/javascript; charset=utf-8")

        # 2. Live Debug Logs Endpoint
        elif parsed.path == '/api/debug/logs':
            limit = int(qs.get("limit", [50])[0])
            self._send_json({"logs": get_live_logs(limit)})

        # 3. Telemetry & Swarm Metrics
        elif parsed.path in ('/api/metrics', '/api/status'):
            lfm_ok = False
            try:
                r = httpx.get(LFM_HEALTH_URL, timeout=0.3)
                lfm_ok = (r.status_code == 200)
            except Exception:
                pass

            metrics = get_hardware_metrics()
            self._send_json({
                "status": {"lfm": lfm_ok},
                "metrics": metrics,
                "topology": SWARM_STATE
            })

        # 4. Autonomous Loop State
        elif parsed.path == '/api/loop/status':
            self._send_json(get_loop_state())

        # 5. Repositories & Git Desktop Engine
        elif parsed.path == '/api/repos':
            repos = find_git_repos()
            self._send_json(repos)

        elif parsed.path == '/api/git/overview':
            repo_path = qs.get("repo_path", [""])[0]
            self._send_json(get_full_github_desktop_state(repo_path))

        elif parsed.path == '/api/git/diff':
            repo_path = qs.get("repo_path", [""])[0]
            file_path = qs.get("file", [""])[0]
            staged = qs.get("staged", ["false"])[0] == "true"
            diff_text = get_file_diff(repo_path, file_path, staged=staged)
            self._send_json({"file": file_path, "diff": diff_text})

        elif parsed.path == '/api/git/commit_detail':
            repo_path = qs.get("repo_path", [""])[0]
            commit_hash = qs.get("hash", [""])[0]
            self._send_json(get_commit_diff(repo_path, commit_hash))

        elif parsed.path == '/api/git/worktrees':
            repo_path = qs.get("repo_path", [""])[0]
            self._send_json({"worktrees": list_worktrees(repo_path)})

        elif parsed.path == '/api/git/stashes':
            repo_path = qs.get("repo_path", [""])[0]
            self._send_json({"stashes": list_stashes(repo_path)})

        # 6. Multi-Chat Sessions
        elif parsed.path == '/api/sessions':
            self._send_json(list_sessions())

        elif parsed.path == '/api/sessions/get':
            sess_id = qs.get("id", [""])[0]
            self._send_json(load_session(sess_id))

        # 7. Artifact Vault (Grouped by Repo)
        elif parsed.path == '/api/artifacts':
            repo_path = qs.get("repo_path", [""])[0]
            self._send_json(scan_all_artifacts(repo_path))

        elif parsed.path == '/api/artifacts/read':
            target_path = qs.get("path", [""])[0]
            if not target_path:
                self._send_json({"error": "Missing path"}, status=400)
                return
            p = Path(unquote(target_path))
            if p.exists() and p.is_file():
                try:
                    content = p.read_text(encoding="utf-8", errors="ignore")
                    self._send_json({"filename": p.name, "path": str(p), "content": content})
                except Exception as e:
                    self._send_json({"error": f"Read error: {e}"}, status=500)
            else:
                self._send_json({"error": "File not found"}, status=404)

        # 8. Models Catalog & Assignments
        elif parsed.path == '/api/models/catalog':
            catalog = scout_all_models(force_refresh=False)
            self._send_json(catalog)

        elif parsed.path == '/api/models/assignments':
            self._send_json(MODEL_ASSIGNMENTS)

        # 9. Dynamic Skills & Capacity Catalog (50+ Skills)
        elif parsed.path == '/api/skills/catalog':
            self._send_json({
                "skills": scan_all_installed_skills(),
                "total_count": len(scan_all_installed_skills())
            })

        # 10. Clean Architecture Rules (Global & Project-Specific)
        elif parsed.path == '/api/rules':
            repo_path = qs.get("repo_path", [""])[0]
            self._send_json({
                "global_rules": get_global_rules(),
                "project_rules": discover_project_rules(repo_path)
            })

        # 11. Multi-Engine Execution Backends Status (Claude Code, AGY, Gemini, Context7, LFM)
        elif parsed.path == '/api/backends/status':
            backends_info = asyncio.run(probe_all_backends())
            self._send_json(backends_info)

        else:
            self.send_error(404, "Not Found")

    def do_POST(self):
        parsed = urlparse(self.path)
        length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(length).decode() if length > 0 else "{}"
        try:
            payload = json.loads(body) if body else {}
        except Exception:
            payload = {}

        # 1. Cost-Based Optimizer (CBO) & Explain Plan
        if parsed.path == '/api/planner/explain':
            msg = payload.get("message", "")
            repo_path = payload.get("repo_path", "")
            ctx = extract_deep_repo_context(repo_path)
            best_plan, candidates, stats = optimize_and_select_best_plan(msg, ctx)
            self._send_json({
                "selected_plan": best_plan.to_dict(),
                "candidates": [c.to_dict() for c in candidates],
                "stats": stats,
                "explain_text": best_plan.generate_explain_plan()
            })

        # 2. Context7 Live Documentation Query
        elif parsed.path == '/api/context7/query':
            lib = payload.get("library", "")
            q = payload.get("query", "")
            log_event("info", "context7", f"API Context7 query for '{lib}' ('{q}')")
            docs_text = fetch_latest_doc_context(lib, q)
            self._send_json({"success": True, "library": lib, "docs": docs_text})

        elif parsed.path == '/api/context7/resolve':
            lib = payload.get("library", "")
            q = payload.get("query", "")
            res = query_context7_library(lib, q)
            self._send_json(res)

        # 3. Autonomous Loop Agent Controls
        elif parsed.path == '/api/loop/start':
            goal = payload.get("goal", "")
            repo_path = payload.get("repo_path", "")
            res = start_loop(goal, repo_path)
            self._send_json(res)

        elif parsed.path == '/api/loop/pause':
            self._send_json(pause_loop())

        elif parsed.path == '/api/loop/resume':
            self._send_json(resume_loop())

        elif parsed.path == '/api/loop/stop':
            self._send_json(stop_loop())

        elif parsed.path == '/api/loop/advisor_ping':
            subagent = payload.get("subagent", "Sub-Agent")
            role = payload.get("role", "dev")
            question = payload.get("question", "")
            context = payload.get("context", "")
            
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            ans = loop.run_until_complete(ping_lead_advisor(subagent, role, question, context))
            loop.close()
            
            self._send_json({"answer": ans})

        # 4. Chat Execution with Dynamic CBO Planning
        elif parsed.path == '/api/chat':
            message = payload.get("message", "")
            repo_path = payload.get("repo_path", "")
            session_id = payload.get("session_id", "")
            log_event("info", "chat", f"Starting chat prompt: '{message[:50]}...'", {"repo": Path(repo_path).name if repo_path else "None"})

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(process_advisor_chat(message, repo_path, session_id))
            loop.close()
            
            self._send_json(result)

        # 5. Multi-Chat Sessions
        elif parsed.path == '/api/sessions/new':
            title = payload.get("title", "New Chat")
            repo_path = payload.get("repo_path", "")
            sess = create_new_session(title, repo_path)
            log_event("info", "session", f"Created new session '{sess['id']}'", {"title": title})
            self._send_json(sess)

        elif parsed.path == '/api/sessions/delete':
            sess_id = payload.get("id", "")
            delete_session(sess_id)
            log_event("info", "session", f"Deleted session '{sess_id}'")
            self._send_json({"status": "deleted"})

        elif parsed.path == '/api/sessions/rename':
            sess_id = payload.get("id", "")
            title = payload.get("title", "")
            rename_session(sess_id, title)
            self._send_json({"status": "renamed"})

        # 6. Git Operations with Comprehensive Debug Logging
        elif parsed.path == '/api/git/commit':
            repo_path = payload.get("repo_path", "")
            msg = payload.get("message", "Commit via Swarm Web")
            files = payload.get("files", [])
            log_event("info", "git", f"Committing changes: '{msg[:40]}'", {"files_count": len(files)})
            if files:
                run_git(repo_path, ["add", "--"] + files)
            else:
                run_git(repo_path, ["add", "-A"])
            res = run_git(repo_path, ["commit", "-m", msg])
            self._send_json(res)

        elif parsed.path == '/api/git/discard':
            repo_path = payload.get("repo_path", "")
            file_path = payload.get("file", "")
            log_event("info", "git", f"Discarding file '{file_path}'")
            stat = run_git(repo_path, ["status", "--porcelain", file_path])
            if "??" in stat.get("stdout", ""):
                res = run_git(repo_path, ["clean", "-f", "--", file_path])
            else:
                res = run_git(repo_path, ["checkout", "HEAD", "--", file_path])
            self._send_json(res)

        elif parsed.path == '/api/git/push':
            repo_path = payload.get("repo_path", "")
            log_event("info", "git", "Executing git push")
            res = run_git(repo_path, ["push"])
            self._send_json(res)

        elif parsed.path == '/api/git/pull':
            repo_path = payload.get("repo_path", "")
            log_event("info", "git", "Executing git pull --rebase")
            res = run_git(repo_path, ["pull", "--rebase"])
            self._send_json(res)

        elif parsed.path == '/api/git/fetch':
            repo_path = payload.get("repo_path", "")
            log_event("info", "git", "Executing git fetch --all")
            res = run_git(repo_path, ["fetch", "--all"])
            self._send_json(res)

        elif parsed.path == '/api/git/branch':
            repo_path = payload.get("repo_path", "")
            branch = payload.get("branch", "")
            create = payload.get("create", False)
            res = switch_or_create_branch(repo_path, branch, create=create)
            self._send_json(res)

        elif parsed.path == '/api/git/worktree/add':
            repo_path = payload.get("repo_path", "")
            wt_path = payload.get("path", "")
            branch = payload.get("branch", "")
            new_branch = payload.get("new_branch", False)
            res = add_worktree(repo_path, wt_path, branch_name=branch, new_branch=new_branch)
            self._send_json(res)

        elif parsed.path == '/api/git/worktree/remove':
            repo_path = payload.get("repo_path", "")
            wt_path = payload.get("path", "")
            force = payload.get("force", False)
            res = remove_worktree(repo_path, wt_path, force=force)
            self._send_json(res)

        # 7. Stash Endpoints
        elif parsed.path == '/api/git/stash/save':
            repo_path = payload.get("repo_path", "")
            msg = payload.get("message", "")
            include_untracked = payload.get("include_untracked", True)
            res = save_stash(repo_path, message=msg, include_untracked=include_untracked)
            self._send_json(res)

        elif parsed.path == '/api/git/stash/pop':
            repo_path = payload.get("repo_path", "")
            index = int(payload.get("index", 0))
            res = pop_stash(repo_path, index=index)
            self._send_json(res)

        elif parsed.path == '/api/git/stash/apply':
            repo_path = payload.get("repo_path", "")
            index = int(payload.get("index", 0))
            res = apply_stash(repo_path, index=index)
            self._send_json(res)

        elif parsed.path == '/api/git/stash/drop':
            repo_path = payload.get("repo_path", "")
            index = int(payload.get("index", 0))
            res = drop_stash(repo_path, index=index)
            self._send_json(res)

        elif parsed.path == '/api/git/stash_and_switch':
            repo_path = payload.get("repo_path", "")
            target_branch = payload.get("branch", "")
            create = payload.get("create", False)
            res = stash_and_switch_branch(repo_path, target_branch, create=create)
            self._send_json(res)

        # 8. Model Scouting & Assignment
        elif parsed.path == '/api/models/rescout':
            catalog = scout_all_models(force_refresh=True)
            log_event("info", "model", "Rescouted models for Gemini & Qwen")
            self._send_json({
                "status": "scouted",
                "catalog": catalog,
                "assignments": MODEL_ASSIGNMENTS
            })

        elif parsed.path == '/api/models/assign':
            target = payload.get("target", "")
            model_id = payload.get("model_id", "")
            if target and model_id:
                MODEL_ASSIGNMENTS[target] = model_id
                save_model_assignments(MODEL_ASSIGNMENTS)
                log_event("info", "model", f"Assigned {target} -> {model_id}")
                self._send_json({"status": "updated", "assignments": MODEL_ASSIGNMENTS})
            else:
                self._send_json({"status": "error", "message": "Missing target or model_id"}, status=400)

        elif parsed.path == '/api/rules/global':
            payload = json.loads(body)
            new_content = payload.get("content", "")
            if new_content:
                ok = save_global_rules(new_content)
                self._send_json({"success": ok, "global_rules": get_global_rules()})
            else:
                self._send_json({"success": False, "error": "Missing content"}, status=400)

        elif parsed.path == '/api/backends/test':
            payload = json.loads(body)
            backend_id = payload.get("backend_id", "claude_code")
            test_res = asyncio.run(test_backend_connection(backend_id))
            self._send_json(test_res)

        else:
            self.send_error(404, "Not Found")

def get_lan_ips() -> List[str]:
    ips = []
    try:
        out = subprocess.check_output(["hostname", "-I"], text=True).strip().split()
        for ip in out:
            if ":" not in ip and not ip.startswith("172.") and not ip.startswith("127."):
                ips.append(ip)
    except Exception:
        pass
    return ips

def run_server(host: str = HOST, port: int = PORT):
    ThreadingHTTPServer.allow_reuse_address = True
    server = ThreadingHTTPServer((host, port), SwarmHandler)
    lan_ips = get_lan_ips()
    log_event("info", "server", f"Swarm AI Studio HTTP Server started on port {port}")
    print("=" * 65)
    print(f"🚀 Swarm AI Studio (Dynamic GPU Swarm & GitHub Desktop) is LIVE:")
    print(f"   • Local:      http://localhost:{port}")
    for ip in lan_ips:
        print(f"   • LAN Access: http://{ip}:{port}")
    print("=" * 65)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping Swarm AI Studio Server...")
        server.server_close()
