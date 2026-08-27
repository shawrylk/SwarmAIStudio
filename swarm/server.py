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

from swarm.config import PORT, HOST, WEB_DIR, LFM_HEALTH_URL, ARTIFACTS_DIR, resolve_within
from swarm.logger import log_event, get_live_logs
from swarm.telemetry import get_hardware_metrics
from swarm.git_engine import (
    find_git_repos,
    get_full_github_desktop_state,
    get_file_diff,
    get_commit_diff,
    git_file_diff,
    git_commit_diff,
    git_status_detailed,
    git_stage_files,
    git_unstage_files,
    git_discard_changes,
    git_commit_staged,
    git_fetch_remote,
    git_pull_remote,
    git_push_remote,
    git_list_branches_detailed,
    git_checkout_branch,
    git_delete_branch,
    git_merge_branch_into_current,
    git_commit_history_detailed,
    git_revert_commit,
    git_reset_commit,
    git_stash_ops,
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
    extract_deep_repo_context,
    gh_issue_create,
    gh_issue_list,
    gh_issue_comment,
    gh_issue_close,
    gh_issue_reopen,
    gh_pr_create
)
from swarm.sessions import (
    list_sessions,
    create_new_session,
    load_session,
    delete_session,
    rename_session,
    list_loop_sessions,
    create_new_loop_session,
    load_loop_session,
    delete_loop_session,
    rename_loop_session
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
    select_loop_session,
    start_loop,
    pause_loop,
    resume_loop,
    stop_loop,
    answer_user_question,
    ping_lead_advisor,
    async_transfer_advisor_to_loop,
    transfer_advisor_to_loop,
    auto_resume_on_startup
)
from swarm.context7_engine import query_context7_library, query_context7_docs, fetch_latest_doc_context
from swarm.planner_cbo import optimize_and_select_best_plan, execute_plan_dag
from swarm.skills_scanner import scan_all_installed_skills, resolve_and_inject_skill
from swarm.rules_engine import get_global_rules, save_global_rules, discover_project_rules
from swarm.engine_bridge import probe_all_backends, test_backend_connection
from swarm.contracts_engine import (
    scan_and_parse_contracts,
    validate_cel_invariants,
    export_to_docusaurus,
    evaluate_cel_expression
)

MODEL_ASSIGNMENTS = load_model_assignments()

# Cache the LFM health probe so the SSE stream doesn't hammer port 8034 every tick.
_LFM_HEALTH_CACHE = {"ok": False, "ts": 0.0}


def _lfm_health(ttl: float = 5.0) -> bool:
    now = time.time()
    if now - _LFM_HEALTH_CACHE["ts"] < ttl:
        return _LFM_HEALTH_CACHE["ok"]
    ok = False
    try:
        r = httpx.get(LFM_HEALTH_URL, timeout=0.3)
        ok = (r.status_code == 200)
    except Exception:
        ok = False
    _LFM_HEALTH_CACHE.update(ok=ok, ts=now)
    return ok


def build_state_snapshot() -> dict:
    """Combined telemetry + topology + loop state — the single real-time payload."""
    return {
        "status": {"lfm": _lfm_health()},
        "metrics": get_hardware_metrics(),
        "topology": SWARM_STATE,
        "loop_state": get_loop_state(),
    }


def _is_active(snapshot: dict) -> bool:
    """True if any agent or the loop is currently running (drives SSE cadence)."""
    running = (snapshot.get("topology", {}) or {}).get("summary", {}).get("running_now", 0)
    loop_status = (snapshot.get("loop_state", {}) or {}).get("status", "")
    return bool(running) or loop_status == "running"


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

    def _serve_sse(self):
        """Stream combined state to the browser over a single long-lived connection."""
        try:
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream')
            self.send_header('Cache-Control', 'no-cache')
            self.send_header('Connection', 'keep-alive')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('X-Accel-Buffering', 'no')  # disable proxy buffering
            self.end_headers()
            # Tell the client how fast to auto-reconnect if the stream drops.
            self.wfile.write(b"retry: 3000\n\n")
            self.wfile.flush()

            while True:
                snap = build_state_snapshot()
                payload = json.dumps(snap)
                self.wfile.write(f"event: state\ndata: {payload}\n\n".encode())
                self.wfile.flush()
                time.sleep(1.0 if _is_active(snap) else 3.0)
        except (BrokenPipeError, ConnectionResetError, OSError):
            return  # client navigated away / closed the tab
        except Exception as e:
            log_event("warn", "server", f"SSE stream ended: {e}")
            return

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

        # 3. Telemetry & Swarm Metrics (one-shot; SSE below is the live channel)
        elif parsed.path in ('/api/metrics', '/api/status'):
            self._send_json(build_state_snapshot())

        # 3b. Real-time state stream (Server-Sent Events).
        #     Replaces per-second polling: the browser opens ONE connection and the
        #     server pushes combined metrics/topology/loop state. Cadence is adaptive
        #     — ~1s while agents run, ~3s when idle — to keep bandwidth low.
        elif parsed.path == '/api/events':
            self._serve_sse()

        # 4. Autonomous Loop State & Sessions
        elif parsed.path == '/api/loop/questions':
            # Questions the escalation ladder parked for the operator. The run
            # keeps working on other tasks while these are outstanding.
            st = get_loop_state()
            qs_all = st.get("pending_user_questions", []) or []
            self._send_json({
                "pending": [q for q in qs_all if not q.get("answered")],
                "answered": [q for q in qs_all if q.get("answered")],
            })

        elif parsed.path == '/api/loop/status':
            self._send_json(get_loop_state())

        elif parsed.path == '/api/loop/sessions' or parsed.path == '/api/loop/sessions/':
            self._send_json(list_loop_sessions())

        elif parsed.path.startswith('/api/loop/sessions/') and not parsed.path.endswith('/select') and not parsed.path.endswith('/new'):
            sess_id = parsed.path.replace('/api/loop/sessions/', '').strip('/')
            sess = load_loop_session(sess_id)
            if sess:
                self._send_json(sess)
            else:
                self._send_json({"error": f"Loop session '{sess_id}' not found"}, status=404)

        elif parsed.path == '/api/loop/sessions/get':
            sess_id = qs.get("id", [""])[0]
            sess = load_loop_session(sess_id) if sess_id else None
            if sess:
                self._send_json(sess)
            else:
                self._send_json(get_loop_state())

        # 5. Repositories & Git Desktop Engine
        elif parsed.path == '/api/repos':
            repos = find_git_repos()
            self._send_json(repos)

        elif parsed.path == '/api/git/status':
            repo_path = qs.get("repo_path", [""])[0]
            self._send_json(git_status_detailed(repo_path))

        elif parsed.path == '/api/git/overview':
            repo_path = qs.get("repo_path", [""])[0]
            self._send_json(get_full_github_desktop_state(repo_path))

        elif parsed.path == '/api/git/branches':
            repo_path = qs.get("repo_path", [""])[0]
            self._send_json({"branches": git_list_branches_detailed(repo_path)})

        elif parsed.path == '/api/git/history':
            repo_path = qs.get("repo_path", [""])[0]
            limit = int(qs.get("limit", [50])[0])
            self._send_json({"history": git_commit_history_detailed(repo_path, limit=limit)})

        elif parsed.path == '/api/git/diff':
            repo_path = qs.get("repo_path", [""])[0]
            file_path = qs.get("file", [""])[0]
            staged = qs.get("staged", ["false"])[0] == "true"
            commit_hash = qs.get("commit", [""])[0]
            diff_text = git_file_diff(repo_path, file_path, staged=staged, commit_hash=commit_hash)
            self._send_json({"file": file_path, "diff": diff_text})

        elif parsed.path == '/api/git/commit_detail':
            repo_path = qs.get("repo_path", [""])[0]
            commit_hash = qs.get("hash", [""])[0] or qs.get("commit", [""])[0]
            self._send_json(git_commit_diff(repo_path, commit_hash))

        elif parsed.path == '/api/git/worktrees':
            repo_path = qs.get("repo_path", [""])[0]
            self._send_json({"worktrees": list_worktrees(repo_path)})

        elif parsed.path == '/api/git/stashes':
            repo_path = qs.get("repo_path", [""])[0]
            self._send_json({"stashes": list_stashes(repo_path)})

        elif parsed.path == '/api/git/issues':
            repo_path = qs.get("repo_path", [""])[0]
            state = qs.get("state", ["open"])[0]
            self._send_json(gh_issue_list(repo_path, state=state))

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
            # SECURITY: confine reads to the artifact vault. The server binds
            # 0.0.0.0 for LAN access, so an unconstrained read would expose any
            # file on the host to every device on the network.
            safe_p = resolve_within(unquote(target_path), ARTIFACTS_DIR)
            if not safe_p:
                self._send_json({"error": "Access denied: path is outside the artifact vault"}, status=403)
                return
            if safe_p.exists() and safe_p.is_file():
                try:
                    content = safe_p.read_text(encoding="utf-8", errors="ignore")
                    self._send_json({"filename": safe_p.name, "path": str(safe_p), "content": content})
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
            skills = scan_all_installed_skills()
            self._send_json({
                "skills": skills,
                "total_count": len(skills)
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

        # 12. Universal Contract Specifications Catalog
        elif parsed.path == '/api/contracts/catalog':
            repo_path = qs.get("repo_path", [""])[0]
            catalog = scan_and_parse_contracts(repo_path)
            self._send_json(catalog)

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

        # 3. Autonomous Loop Agent Controls & Sessions
        elif parsed.path == '/api/loop/start':
            goal = payload.get("goal", "")
            repo_path = payload.get("repo_path", "")
            session_id = payload.get("session_id", None)
            advisor_session_id = payload.get("advisor_session_id", "")
            res = start_loop(goal, repo_path, session_id=session_id, advisor_session_id=advisor_session_id)
            self._send_json(res)

        elif parsed.path == '/api/loop/pause':
            self._send_json(pause_loop())

        elif parsed.path == '/api/loop/resume':
            sess_id = payload.get("session_id")
            self._send_json(resume_loop(session_id=sess_id))

        elif parsed.path == '/api/loop/stop':
            self._send_json(stop_loop())

        elif parsed.path == '/api/loop/answer':
            # Answer a task the escalation ladder parked for the operator. The
            # answer becomes authoritative guidance and the task is requeued, so
            # a run that hit the end of its automated tiers can continue.
            task_id = (payload.get("task_id") or "").strip()
            answer = (payload.get("answer") or "").strip()
            if not task_id or not answer:
                self._send_json({"success": False, "error": "task_id and answer are required"}, status=400)
            else:
                self._send_json(answer_user_question(task_id, answer))

        elif parsed.path == '/api/loop/sessions/new':
            title = payload.get("title", "New Auto-Dev Loop")
            goal = payload.get("goal", "")
            repo_path = payload.get("repo_path", "")
            advisor_session_id = payload.get("advisor_session_id", "")
            sess = create_new_loop_session(title=title, goal=goal, repo_path=repo_path, advisor_session_id=advisor_session_id)
            select_loop_session(sess["id"])
            log_event("info", "loop_session", f"Created new loop session '{sess['id']}'", {"title": title})
            self._send_json(sess)

        elif parsed.path == '/api/loop/sessions/select' or (parsed.path.startswith('/api/loop/sessions/') and parsed.path.endswith('/select')):
            if parsed.path == '/api/loop/sessions/select':
                sess_id = payload.get("id") or payload.get("session_id", "")
            else:
                sess_id = parsed.path.replace('/api/loop/sessions/', '').replace('/select', '').strip('/')
            state = select_loop_session(sess_id)
            log_event("info", "loop_session", f"Selected active loop session '{sess_id}'")
            self._send_json({"success": True, "session_id": sess_id, "state": state})

        elif parsed.path == '/api/loop/sessions/delete':
            sess_id = payload.get("id") or payload.get("session_id", "")
            delete_loop_session(sess_id)
            log_event("info", "loop_session", f"Deleted loop session '{sess_id}'")
            self._send_json({"status": "deleted"})

        elif parsed.path == '/api/loop/sessions/rename':
            sess_id = payload.get("id") or payload.get("session_id", "")
            title = payload.get("title", "")
            rename_loop_session(sess_id, title)
            self._send_json({"status": "renamed"})

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

        elif parsed.path == '/api/advisor/transfer_to_loop':
            adv_sess_id = payload.get("session_id", "")
            custom_goal = payload.get("custom_goal", "")
            auto_start = payload.get("auto_start", True)
            repo_path = payload.get("repo_path", "")
            
            log_event("info", "transfer", f"Transferring Advisor session '{adv_sess_id}' to Auto-Dev Loop", {"auto_start": auto_start})
            
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                transfer_res = loop.run_until_complete(
                    async_transfer_advisor_to_loop(
                        session_id=adv_sess_id,
                        custom_goal=custom_goal,
                        auto_start=auto_start,
                        repo_path=repo_path
                    )
                )
                self._send_json(transfer_res)
            except Exception as e:
                log_event("error", "transfer", f"Transfer to loop failed: {e}")
                self._send_json({"success": False, "error": str(e)}, status=500)
            finally:
                loop.close()

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
        elif parsed.path == '/api/git/stage':
            repo_path = payload.get("repo_path", "")
            files = payload.get("files", [])
            self._send_json(git_stage_files(repo_path, files))

        elif parsed.path == '/api/git/unstage':
            repo_path = payload.get("repo_path", "")
            files = payload.get("files", [])
            self._send_json(git_unstage_files(repo_path, files))

        elif parsed.path == '/api/git/commit':
            repo_path = payload.get("repo_path", "")
            summary = payload.get("summary") or payload.get("message", "Commit via Swarm Web")
            desc = payload.get("description", "")
            files = payload.get("files", [])
            author_name = payload.get("author_name", "Swarm AI Studio")
            author_email = payload.get("author_email", "swarm@ai.studio")
            if files:
                git_stage_files(repo_path, files)
            res = git_commit_staged(repo_path, summary, desc, author_name=author_name, author_email=author_email)
            self._send_json(res)

        elif parsed.path == '/api/git/discard':
            repo_path = payload.get("repo_path", "")
            files = payload.get("files")
            if files is None and "file" in payload:
                files = [payload["file"]]
            res = git_discard_changes(repo_path, files)
            self._send_json(res)

        elif parsed.path == '/api/git/push':
            repo_path = payload.get("repo_path", "")
            branch = payload.get("branch", "")
            force = payload.get("force", False)
            set_upstream = payload.get("set_upstream", False)
            self._send_json(git_push_remote(repo_path, branch=branch, force=force, set_upstream=set_upstream))

        elif parsed.path == '/api/git/pull':
            repo_path = payload.get("repo_path", "")
            rebase = payload.get("rebase", False)
            self._send_json(git_pull_remote(repo_path, rebase=rebase))

        elif parsed.path == '/api/git/fetch':
            repo_path = payload.get("repo_path", "")
            self._send_json(git_fetch_remote(repo_path))

        elif parsed.path in ('/api/git/branch', '/api/git/branch/checkout'):
            repo_path = payload.get("repo_path", "")
            branch = payload.get("branch", "")
            create = payload.get("create", False)
            start_point = payload.get("start_point", "")
            res = git_checkout_branch(repo_path, branch, create_if_missing=create, start_point=start_point)
            self._send_json(res)

        elif parsed.path == '/api/git/branch/create':
            repo_path = payload.get("repo_path", "")
            branch = payload.get("branch", "")
            start_point = payload.get("start_point", "")
            res = git_checkout_branch(repo_path, branch, create_if_missing=True, start_point=start_point)
            self._send_json(res)

        elif parsed.path == '/api/git/branch/delete':
            repo_path = payload.get("repo_path", "")
            branch = payload.get("branch", "")
            force = payload.get("force", False)
            res = git_delete_branch(repo_path, branch, force=force)
            self._send_json(res)

        elif parsed.path == '/api/git/branch/merge':
            repo_path = payload.get("repo_path", "")
            source_branch = payload.get("source_branch") or payload.get("branch", "")
            message = payload.get("message", "")
            res = git_merge_branch_into_current(repo_path, source_branch, message=message)
            self._send_json(res)

        elif parsed.path == '/api/git/commit/revert':
            repo_path = payload.get("repo_path", "")
            commit_sha = payload.get("commit_sha") or payload.get("hash", "")
            res = git_revert_commit(repo_path, commit_sha)
            self._send_json(res)

        elif parsed.path == '/api/git/commit/reset':
            repo_path = payload.get("repo_path", "")
            commit_sha = payload.get("commit_sha") or payload.get("hash", "")
            mode = payload.get("mode", "soft")
            res = git_reset_commit(repo_path, commit_sha, mode=mode)
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
        elif parsed.path == '/api/git/stash':
            repo_path = payload.get("repo_path", "")
            op = payload.get("op", "save")
            msg = payload.get("message", "")
            index = int(payload.get("index", 0))
            target_branch = payload.get("target_branch") or payload.get("branch", "")
            create = payload.get("create", False)
            res = git_stash_ops(repo_path, op=op, message=msg, index=index, target_branch=target_branch, create=create)
            self._send_json(res)

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

        elif parsed.path == '/api/git/issue/create':
            repo_path = payload.get("repo_path", "")
            title = payload.get("title", "")
            body = payload.get("body", "")
            labels = payload.get("labels", [])
            res = gh_issue_create(repo_path, title, body, labels=labels)
            self._send_json(res)

        elif parsed.path == '/api/git/issue/comment':
            repo_path = payload.get("repo_path", "")
            num = payload.get("issue_number") or payload.get("number", "")
            comment = payload.get("comment", "")
            res = gh_issue_comment(repo_path, num, comment)
            self._send_json(res)

        elif parsed.path == '/api/git/issue/close':
            repo_path = payload.get("repo_path", "")
            num = payload.get("issue_number") or payload.get("number", "")
            comment = payload.get("comment", "")
            reason = payload.get("reason", "completed")
            res = gh_issue_close(repo_path, num, comment=comment, reason=reason)
            self._send_json(res)

        elif parsed.path == '/api/git/issue/reopen':
            repo_path = payload.get("repo_path", "")
            num = payload.get("issue_number") or payload.get("number", "")
            comment = payload.get("comment", "")
            res = gh_issue_reopen(repo_path, num, comment=comment)
            self._send_json(res)

        elif parsed.path == '/api/git/pr/create':
            repo_path = payload.get("repo_path", "")
            title = payload.get("title", "")
            body = payload.get("body", "")
            base = payload.get("base", "main")
            head = payload.get("head", "")
            res = gh_pr_create(repo_path, title, body, base=base, head=head)
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

        elif parsed.path == '/api/skills/resolve':
            role = payload.get("role", "dev")
            task_desc = payload.get("task", "")
            repo_path = payload.get("repo_path", "")
            skill_info = resolve_and_inject_skill(role, task_desc, repo_path)
            self._send_json(skill_info)

        # 9. Contracts Validation & Docusaurus Documentation Export
        elif parsed.path == '/api/contracts/validate':
            rules = payload.get("invariants") or payload.get("rules", [])
            context = payload.get("context") or payload.get("state") or payload.get("payload", {})
            repo_path = payload.get("repo_path", "")
            
            if not rules and repo_path:
                catalog = scan_and_parse_contracts(repo_path)
                rules = catalog.get("cel_invariants", [])

            val_res = validate_cel_invariants(rules, context)
            self._send_json(val_res)

        elif parsed.path == '/api/contracts/export_docusaurus':
            repo_path = payload.get("repo_path", "")
            output_dir = payload.get("output_dir", "")
            if not output_dir:
                if repo_path:
                    output_dir = str(Path(repo_path) / "docs")
                else:
                    output_dir = str(WEB_DIR / "docs")
            
            res = export_to_docusaurus(repo_path, output_dir)
            self._send_json(res)

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

    # Auto-detect interrupted loop runs and auto-resume if configured
    try:
        auto_resume_on_startup()
    except Exception as e:
        log_event("error", "recovery", f"Auto-resume on startup error: {e}")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping Swarm AI Studio Server...")
        server.server_close()
