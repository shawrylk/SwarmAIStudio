"""
Swarm AI Studio HTTP Server & API Dispatcher
Serves frontend assets from web/ and dispatches JSON API routes.
"""

import json
import asyncio
import subprocess
from pathlib import Path
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, unquote
from typing import List
import httpx

from swarm.config import PORT, HOST, WEB_DIR, LFM_HEALTH_URL
from swarm.telemetry import get_hardware_metrics
from swarm.git_engine import (
    find_git_repos,
    get_full_github_desktop_state,
    get_file_diff,
    get_commit_diff,
    run_git
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

        # 2. Telemetry & Swarm Metrics
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

        # 3. Repositories & Git Desktop Engine
        elif parsed.path == '/api/repos':
            self._send_json(find_git_repos())
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

        # 4. Multi-Chat Sessions
        elif parsed.path == '/api/sessions':
            self._send_json(list_sessions())
        elif parsed.path == '/api/sessions/get':
            sess_id = qs.get("id", [""])[0]
            self._send_json(load_session(sess_id))

        # 5. Artifact Vault
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

        # 6. Models Catalog & Assignments
        elif parsed.path == '/api/models/catalog':
            catalog = scout_all_models(force_refresh=False)
            self._send_json(catalog)
        elif parsed.path == '/api/models/assignments':
            self._send_json(MODEL_ASSIGNMENTS)

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

        # 1. Chat Execution
        if parsed.path == '/api/chat':
            message = payload.get("message", "")
            repo_path = payload.get("repo_path", "")
            session_id = payload.get("session_id", "")
            
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(process_advisor_chat(message, repo_path, session_id))
            loop.close()
            
            self._send_json(result)

        # 2. Multi-Chat Sessions
        elif parsed.path == '/api/sessions/new':
            title = payload.get("title", "New Chat")
            repo_path = payload.get("repo_path", "")
            sess = create_new_session(title, repo_path)
            self._send_json(sess)

        elif parsed.path == '/api/sessions/delete':
            sess_id = payload.get("id", "")
            delete_session(sess_id)
            self._send_json({"status": "deleted"})

        elif parsed.path == '/api/sessions/rename':
            sess_id = payload.get("id", "")
            title = payload.get("title", "")
            rename_session(sess_id, title)
            self._send_json({"status": "renamed"})

        # 3. Git Operations
        elif parsed.path == '/api/git/commit':
            repo_path = payload.get("repo_path", "")
            msg = payload.get("message", "Commit via Swarm Web")
            files = payload.get("files", [])
            if files:
                run_git(repo_path, ["add", "--"] + files)
            else:
                run_git(repo_path, ["add", "-A"])
            res = run_git(repo_path, ["commit", "-m", msg])
            self._send_json(res)

        elif parsed.path == '/api/git/discard':
            repo_path = payload.get("repo_path", "")
            file_path = payload.get("file", "")
            stat = run_git(repo_path, ["status", "--porcelain", file_path])
            if "??" in stat.get("stdout", ""):
                res = run_git(repo_path, ["clean", "-f", "--", file_path])
            else:
                res = run_git(repo_path, ["checkout", "HEAD", "--", file_path])
            self._send_json(res)

        elif parsed.path == '/api/git/push':
            repo_path = payload.get("repo_path", "")
            res = run_git(repo_path, ["push"])
            self._send_json(res)

        elif parsed.path == '/api/git/pull':
            repo_path = payload.get("repo_path", "")
            res = run_git(repo_path, ["pull", "--rebase"])
            self._send_json(res)

        elif parsed.path == '/api/git/fetch':
            repo_path = payload.get("repo_path", "")
            res = run_git(repo_path, ["fetch", "--all"])
            self._send_json(res)

        elif parsed.path == '/api/git/branch':
            repo_path = payload.get("repo_path", "")
            branch = payload.get("branch", "")
            create = payload.get("create", False)
            args = ["checkout", "-b", branch] if create else ["checkout", branch]
            res = run_git(repo_path, args)
            self._send_json(res)

        elif parsed.path == '/api/git/worktree/add':
            repo_path = payload.get("repo_path", "")
            wt_path = payload.get("path", "")
            branch = payload.get("branch", "")
            args = ["worktree", "add", wt_path] + ([branch] if branch else [])
            res = run_git(repo_path, args)
            self._send_json(res)

        elif parsed.path == '/api/git/stash/save':
            repo_path = payload.get("repo_path", "")
            msg = payload.get("message", "")
            args = ["stash", "push"] + (["-m", msg] if msg else [])
            res = run_git(repo_path, args)
            self._send_json(res)

        # 4. Model Scouting & Assignment
        elif parsed.path == '/api/models/rescout':
            catalog = scout_all_models(force_refresh=True)
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
                self._send_json({"status": "updated", "assignments": MODEL_ASSIGNMENTS})
            else:
                self._send_json({"status": "error", "message": "Missing target or model_id"}, status=400)

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
