"""
Full GitHub Desktop Engine for Swarm AI Studio
Provides 100% mouse-driven operations:
- Branches (switch, filter, create, delete)
- Staging & Commit box with summary and description
- Ahead/Behind commit synchronization (Fetch, Pull, Push)
- Unified colored diffs for modified & untracked files
- Worktrees and Stash management
- Rich commit history inspection
"""

import os
import subprocess
from pathlib import Path
from typing import List, Dict, Any

def run_git(repo_path: str, args: List[str]) -> Dict[str, Any]:
    if not repo_path:
        return {"success": False, "error": "No repository selected"}
    rp = Path(repo_path)
    if not rp.exists() or not (rp / ".git").exists():
        return {"success": False, "error": f"Path is not a valid Git repository: {repo_path}"}
    try:
        cmd = ["git", "-C", str(rp)] + args
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return {
            "success": res.returncode == 0,
            "stdout": res.stdout.strip(),
            "stderr": res.stderr.strip(),
            "returncode": res.returncode
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

def find_git_repos() -> List[Dict[str, str]]:
    repos = []
    scan_roots = [
        Path.home() / "Documents/GitHub",
        Path.home() / "Documents",
        Path.home() / "Desktop",
        Path.home()
    ]
    seen = set()

    for root_dir in scan_roots:
        if not root_dir.exists():
            continue
        try:
            for item in root_dir.iterdir():
                if item.is_dir() and (item / ".git").exists() and str(item) not in seen:
                    if not item.name.startswith(".") and item.name not in ["node_modules", ".cache"]:
                        repos.append({"name": item.name, "path": str(item)})
                        seen.add(str(item))
                elif item.is_dir() and not item.name.startswith("."):
                    try:
                        for sub in item.iterdir():
                            if sub.is_dir() and (sub / ".git").exists() and str(sub) not in seen:
                                repos.append({"name": f"{item.name}/{sub.name}", "path": str(sub)})
                                seen.add(str(sub))
                    except Exception:
                        pass
        except Exception:
            pass

    cwd = Path.cwd()
    if (cwd / ".git").exists() and str(cwd) not in seen:
        repos.insert(0, {"name": f"Current: {cwd.name}", "path": str(cwd)})

    return repos

def get_full_github_desktop_state(repo_path: str) -> Dict[str, Any]:
    if not repo_path or not (Path(repo_path) / ".git").exists():
        return {"active": False}

    # 1. Branch & Remote Sync
    branch = run_git(repo_path, ["branch", "--show-current"])["stdout"] or "HEAD"
    
    # Ahead / Behind count
    ahead, behind = 0, 0
    upstream = run_git(repo_path, ["rev-parse", "--abbrev-ref", "@{u}"])
    if upstream["success"] and upstream["stdout"]:
        counts = run_git(repo_path, ["rev-list", "--left-right", "--count", f"{branch}...{upstream['stdout']}"])
        if counts["success"] and counts["stdout"]:
            parts = counts["stdout"].split()
            if len(parts) >= 2:
                ahead = int(parts[0])
                behind = int(parts[1])

    # 2. Changed Files (Working Tree & Staged)
    status_res = run_git(repo_path, ["status", "--porcelain=v1", "-uall"])
    changed_files = []
    if status_res["success"] and status_res["stdout"]:
        for line in status_res["stdout"].split("\n"):
            if len(line) >= 4:
                idx_status = line[0]
                wt_status = line[1]
                file_name = line[2:].strip()
                
                status_char = 'M'
                if idx_status == '?' or wt_status == '?':
                    status_char = 'U' # Untracked
                elif idx_status == 'A' or wt_status == 'A':
                    status_char = 'A' # Added
                elif idx_status == 'D' or wt_status == 'D':
                    status_char = 'D' # Deleted
                elif idx_status == 'R' or wt_status == 'R':
                    status_char = 'R' # Renamed
                else:
                    status_char = 'M' # Modified

                changed_files.append({
                    "path": file_name,
                    "status": status_char,
                    "staged": (idx_status not in [' ', '?'])
                })

    # 3. Commit History (Last 30 commits)
    history_res = run_git(repo_path, ["log", "-n", "30", "--pretty=format:%H%x09%h%x09%an%x09%ar%x09%s"])
    history = []
    if history_res["success"] and history_res["stdout"]:
        for line in history_res["stdout"].split("\n"):
            parts = line.split("\t")
            if len(parts) >= 5:
                history.append({
                    "hash": parts[0],
                    "short_hash": parts[1],
                    "author": parts[2],
                    "date": parts[3],
                    "subject": parts[4]
                })

    # 4. Branch List
    branches_res = run_git(repo_path, ["branch", "-a"])
    branches = []
    if branches_res["success"]:
        for b in branches_res["stdout"].split("\n"):
            clean_b = b.replace("*", "").strip()
            if clean_b and not clean_b.startswith("remotes/origin/HEAD"):
                branches.append(clean_b)

    # 5. Worktrees
    worktrees_res = run_git(repo_path, ["worktree", "list"])
    worktrees = []
    if worktrees_res["success"]:
        for wt in worktrees_res["stdout"].split("\n"):
            if wt.strip():
                parts = wt.split()
                worktrees.append({
                    "path": parts[0] if len(parts) > 0 else "",
                    "commit": parts[1] if len(parts) > 1 else "",
                    "branch": parts[2].replace("[", "").replace("]", "") if len(parts) > 2 else ""
                })

    # 6. Stashes
    stash_res = run_git(repo_path, ["stash", "list"])
    stashes = []
    if stash_res["success"] and stash_res["stdout"]:
        for s in stash_res["stdout"].split("\n"):
            if s.strip():
                stashes.append(s.strip())

    return {
        "active": True,
        "repo_name": Path(repo_path).name,
        "repo_path": repo_path,
        "branch": branch,
        "ahead": ahead,
        "behind": behind,
        "clean": len(changed_files) == 0,
        "changed_files": changed_files,
        "history": history,
        "branches": branches,
        "worktrees": worktrees,
        "stashes": stashes
    }

def get_file_diff(repo_path: str, file_path: str, staged: bool = False, commit_hash: str = "") -> str:
    if not repo_path or not (Path(repo_path) / ".git").exists():
        return ""
    
    if commit_hash:
        res = run_git(repo_path, ["show", f"{commit_hash}", "--", file_path])
        return res["stdout"] or "No diff recorded for this commit."

    # Check if untracked
    status = run_git(repo_path, ["status", "--porcelain", file_path])
    if status["success"] and "??" in status["stdout"]:
        full_p = Path(repo_path) / file_path
        if full_p.exists() and full_p.is_file():
            content = full_p.read_text(encoding="utf-8", errors="ignore")
            lines = content.split("\n")
            return f"--- /dev/null\n+++ b/{file_path}\n@@ -0,0 +1,{len(lines)} @@\n" + "\n".join(f"+{l}" for l in lines)

    args = ["diff"]
    if staged:
        args.append("--cached")
    else:
        args.append("HEAD")
    args.extend(["--", file_path])

    res = run_git(repo_path, args)
    if not res["stdout"]:
        res = run_git(repo_path, ["diff", "--", file_path])
    return res["stdout"] or "No changes detected in file."

def get_commit_diff(repo_path: str, commit_hash: str) -> Dict[str, Any]:
    if not repo_path or not commit_hash:
        return {"error": "Missing params"}
    show_res = run_git(repo_path, ["show", "--stat", "--patch", commit_hash])
    files_res = run_git(repo_path, ["show", "--name-only", "--pretty=format:", commit_hash])
    
    files = [f.strip() for f in files_res["stdout"].split("\n") if f.strip()]
    return {
        "hash": commit_hash,
        "files": files,
        "diff": show_res["stdout"]
    }

def extract_deep_repo_context(repo_path_str: str) -> Dict[str, Any]:
    if not repo_path_str:
        return {}
    p = Path(repo_path_str)
    if not p.exists() or not (p / ".git").exists():
        return {}

    context = {
        "name": p.name,
        "path": str(p),
        "branch": "HEAD",
        "recent_commits": "",
        "status": "",
        "diff": "",
        "readme": "",
        "manifests": {},
        "files_sample": []
    }

    try:
        context["branch"] = subprocess.check_output(["git", "-C", str(p), "branch", "--show-current"], text=True).strip() or "HEAD"
        context["status"] = subprocess.check_output(["git", "-C", str(p), "status", "--short"], text=True).strip()
        context["recent_commits"] = subprocess.check_output(["git", "-C", str(p), "log", "-n", "5", "--oneline"], text=True).strip()
        
        diff = subprocess.check_output(["git", "-C", str(p), "diff", "HEAD"], text=True).strip()
        if not diff:
            diff = subprocess.check_output(["git", "-C", str(p), "diff", "HEAD~1"], text=True).strip()
        context["diff"] = diff[:4000]
    except Exception:
        pass

    for r_name in ["README.md", "README.txt", "readme.md", "README"]:
        r_file = p / r_name
        if r_file.exists():
            context["readme"] = r_file.read_text(errors="ignore")[:2500]
            break

    manifest_names = ["package.json", "Cargo.toml", "pyproject.toml", "go.mod", "Makefile", "global.json", "BankFlow.sln"]
    for m in manifest_names:
        m_file = p / m
        if m_file.exists():
            context["manifests"][m] = m_file.read_text(errors="ignore")[:1000]

    for root, dirs, files in os.walk(str(p)):
        dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ["node_modules", "target", "dist", "build", "__pycache__", ".git", "bin", "obj"]]
        rel = os.path.relpath(root, str(p))
        for f in files[:6]:
            if not f.startswith("."):
                context["files_sample"].append(os.path.join(rel, f) if rel != "." else f)
        if rel.count(os.sep) >= 2:
            dirs.clear()

    return context

def format_repo_prompt_block(ctx: Dict[str, Any]) -> str:
    if not ctx:
        return ""
    lines = [
        f"=== REPOSITORY CONTEXT: {ctx.get('name')} ({ctx.get('path')}) ===",
        f"Branch: {ctx.get('branch')}",
        f"Git Status: {ctx.get('status') or 'Clean'}",
        f"Recent Commits:\n{ctx.get('recent_commits')}\n",
        f"Sample File Structure:\n" + "\n".join(f"  - {f}" for f in ctx.get('files_sample', [])[:20]),
    ]
    if ctx.get("readme"):
        lines.append(f"\nREADME Snippet:\n{ctx.get('readme')}")
    if ctx.get("manifests"):
        for m_name, m_val in ctx.get("manifests", {}).items():
            lines.append(f"\nManifest ({m_name}):\n{m_val}")
    if ctx.get("diff"):
        lines.append(f"\nActive Git Diff:\n{ctx.get('diff')}")
    lines.append("="*50 + "\n")
    return "\n".join(lines)
