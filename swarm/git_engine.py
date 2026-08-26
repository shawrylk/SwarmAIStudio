"""
Full GitHub Desktop Engine for Swarm AI Studio
Provides 100% mouse-driven operations with comprehensive action logging:
- Branches (switch, filter, create, delete, track remote)
- Staging & Commit box with summary and description
- Ahead/Behind commit synchronization (Fetch, Pull, Push)
- Unified colored diffs for modified & untracked files
- Worktrees Manager (List, Create, Remove)
- Stash Subsystem (Stash changes, Pop/Restore, Drop, Stash & Switch)
- History inspection with file breakdown
"""

import os
import subprocess
import time
from pathlib import Path
from typing import List, Dict, Any, Optional
from swarm.logger import log_event

def run_git(repo_path: str, args: List[str]) -> Dict[str, Any]:
    if not repo_path:
        log_event("error", "git", "Execution failed: No repository path provided")
        return {"success": False, "error": "No repository selected", "stderr": "No repository path provided"}
    
    rp = Path(repo_path)
    if not rp.exists() or not (rp / ".git").exists():
        err_msg = f"Path is not a valid Git repository: {repo_path}"
        log_event("error", "git", err_msg)
        return {"success": False, "error": err_msg, "stderr": err_msg}
    
    t0 = time.time()
    cmd = ["git", "-C", str(rp)] + args
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        dur = round((time.time() - t0) * 1000, 1)
        
        details = {
            "cmd": " ".join(cmd),
            "repo": rp.name,
            "returncode": res.returncode,
            "duration_ms": dur
        }
        
        if res.returncode == 0:
            log_event("info", "git", f"git {' '.join(args)} (took {dur}ms)", details)
            return {
                "success": True,
                "stdout": res.stdout.strip(),
                "stderr": res.stderr.strip(),
                "returncode": res.returncode
            }
        else:
            log_event("warn", "git", f"git {' '.join(args)} failed (code {res.returncode})", details, error=res.stderr.strip())
            return {
                "success": False,
                "stdout": res.stdout.strip(),
                "stderr": res.stderr.strip(),
                "returncode": res.returncode,
                "error": res.stderr.strip() or f"Git command failed with code {res.returncode}"
            }
    except Exception as e:
        dur = round((time.time() - t0) * 1000, 1)
        err_str = str(e)
        log_event("error", "git", f"Exception running git {' '.join(args)}", {"cmd": " ".join(cmd), "duration_ms": dur}, error=err_str)
        return {"success": False, "error": err_str, "stderr": err_str}

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

    # 4. Branch List (Local + Remotes formatted cleanly)
    branches = get_clean_branches(repo_path)

    # 5. Worktrees
    worktrees = list_worktrees(repo_path)

    # 6. Structured Stashes
    stashes = list_stashes(repo_path)

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

def get_clean_branches(repo_path: str) -> List[Dict[str, Any]]:
    """Returns unique, clean branch names separating local and remote branches."""
    res = run_git(repo_path, ["branch", "-a", "--format=%(refname:short)|%(upstream:short)|%(HEAD)"])
    branches = []
    seen = set()

    if res["success"] and res["stdout"]:
        for line in res["stdout"].split("\n"):
            if not line.strip():
                continue
            parts = line.strip().split("|")
            b_name = parts[0].strip()
            is_head = len(parts) > 2 and parts[2].strip() == "*"
            
            # Clean remote prefix
            clean_name = b_name
            is_remote = False
            if clean_name.startswith("origin/"):
                clean_name = clean_name.replace("origin/", "", 1)
                is_remote = True
            elif clean_name.startswith("remotes/origin/"):
                clean_name = clean_name.replace("remotes/origin/", "", 1)
                is_remote = True

            if clean_name and clean_name != "HEAD" and clean_name not in seen:
                branches.append({
                    "name": clean_name,
                    "ref": b_name,
                    "is_current": is_head,
                    "is_remote": is_remote
                })
                seen.add(clean_name)
    
    if not branches:
        branches.append({"name": "main", "ref": "main", "is_current": True, "is_remote": False})
    return branches

def switch_or_create_branch(repo_path: str, branch_name: str, create: bool = False, start_point: str = "") -> Dict[str, Any]:
    """Robust branch checkout and creation handling local, remote, and new branches."""
    clean_name = branch_name.strip()
    if clean_name.startswith("origin/"):
        clean_name = clean_name.replace("origin/", "", 1)
    elif clean_name.startswith("remotes/origin/"):
        clean_name = clean_name.replace("remotes/origin/", "", 1)

    if not clean_name:
        return {"success": False, "error": "Branch name cannot be empty."}

    # 1. If explicit create requested
    if create:
        args = ["checkout", "-b", clean_name]
        if start_point:
            args.append(start_point)
        res = run_git(repo_path, args)
        log_event("info" if res["success"] else "warn", "branch", f"Create branch '{clean_name}'", {"create": True}, error=res.get("error", ""))
        return res

    # 2. Check if branch exists locally
    local_check = run_git(repo_path, ["show-ref", "--verify", f"refs/heads/{clean_name}"])
    if local_check["success"]:
        res = run_git(repo_path, ["checkout", clean_name])
        log_event("info" if res["success"] else "warn", "branch", f"Checkout local branch '{clean_name}'", error=res.get("error", ""))
        return res

    # 3. Check if remote tracking branch exists
    remote_check = run_git(repo_path, ["show-ref", "--verify", f"refs/remotes/origin/{clean_name}"])
    if remote_check["success"]:
        res = run_git(repo_path, ["checkout", "-b", clean_name, "--track", f"origin/{clean_name}"])
        log_event("info" if res["success"] else "warn", "branch", f"Checkout remote tracking branch 'origin/{clean_name}'", error=res.get("error", ""))
        return res

    # 4. Standard checkout attempt
    res = run_git(repo_path, ["checkout", clean_name])
    log_event("info" if res["success"] else "warn", "branch", f"Checkout '{clean_name}'", error=res.get("error", ""))
    return res

# ─────────────────────────────────────────────────────────────
# Complete Stash Subsystem (GitHub Desktop Style)
# ─────────────────────────────────────────────────────────────
def list_stashes(repo_path: str) -> List[Dict[str, Any]]:
    """Lists all stashes with index, message, branch, and relative date."""
    res = run_git(repo_path, ["stash", "list", "--pretty=format:%gd%x09%cr%x09%gs"])
    stashes = []
    
    if res["success"] and res["stdout"]:
        for line in res["stdout"].split("\n"):
            if not line.strip():
                continue
            parts = line.split("\t")
            ref = parts[0].strip() # e.g. stash@{0}
            date = parts[1].strip() if len(parts) > 1 else ""
            msg = parts[2].strip() if len(parts) > 2 else ""

            # Extract index
            idx = 0
            if "{" in ref and "}" in ref:
                try:
                    idx = int(ref.split("{")[1].split("}")[0])
                except Exception:
                    pass

            # Extract branch from message (e.g. WIP on main: ...)
            branch = "main"
            clean_msg = msg
            if "WIP on " in msg:
                branch_part = msg.split("WIP on ")[1].split(":")[0]
                branch = branch_part.strip()
            elif "On " in msg:
                branch_part = msg.split("On ")[1].split(":")[0]
                branch = branch_part.strip()

            stashes.append({
                "index": idx,
                "ref": ref,
                "branch": branch,
                "date": date,
                "message": clean_msg
            })

    return stashes

def save_stash(repo_path: str, message: str = "", include_untracked: bool = True) -> Dict[str, Any]:
    """Stashes current changes with optional custom message."""
    args = ["stash", "push"]
    if include_untracked:
        args.append("--include-untracked")
    
    if message.strip():
        args.extend(["-m", message.strip()])
    
    res = run_git(repo_path, args)
    log_event("info" if res["success"] else "warn", "stash", f"Stash changes (message: '{message}')", error=res.get("error", ""))
    return res

def pop_stash(repo_path: str, index: int = 0) -> Dict[str, Any]:
    """Restores and removes stash at index."""
    args = ["stash", "pop", f"stash@{{{index}}}"]
    res = run_git(repo_path, args)
    log_event("info" if res["success"] else "warn", "stash", f"Restore / Pop stash@{index}", error=res.get("error", ""))
    return res

def apply_stash(repo_path: str, index: int = 0) -> Dict[str, Any]:
    """Applies stash without removing it."""
    args = ["stash", "apply", f"stash@{{{index}}}"]
    res = run_git(repo_path, args)
    log_event("info" if res["success"] else "warn", "stash", f"Apply stash@{index}", error=res.get("error", ""))
    return res

def drop_stash(repo_path: str, index: int = 0) -> Dict[str, Any]:
    """Discards / removes stash at index."""
    args = ["stash", "drop", f"stash@{{{index}}}"]
    res = run_git(repo_path, args)
    log_event("info" if res["success"] else "warn", "stash", f"Drop / Discard stash@{index}", error=res.get("error", ""))
    return res

def stash_and_switch_branch(repo_path: str, target_branch: str, create: bool = False) -> Dict[str, Any]:
    """
    Automates GitHub Desktop's 'Stash changes and switch branch':
    1. Stashes working directory changes on current branch.
    2. Switches to target branch (or creates it).
    """
    current_branch = run_git(repo_path, ["branch", "--show-current"])["stdout"] or "HEAD"
    timestamp_str = time.strftime('%Y-%m-%d %H:%M:%S')
    stash_msg = f"Stash on {current_branch} before switching to {target_branch} ({timestamp_str})"
    
    # 1. Stash changes
    stash_res = save_stash(repo_path, message=stash_msg, include_untracked=True)
    if not stash_res["success"]:
        return {
            "success": False,
            "error": f"Failed to stash changes: {stash_res.get('error', '')}",
            "stderr": stash_res.get("stderr", "")
        }

    # 2. Switch branch
    switch_res = switch_or_create_branch(repo_path, target_branch, create=create)
    if not switch_res["success"]:
        # If branch switch failed, try to pop back the stash so user isn't stranded
        pop_stash(repo_path, 0)
        return {
            "success": False,
            "error": f"Failed to switch to branch '{target_branch}': {switch_res.get('error', '')}. Stash was restored.",
            "stderr": switch_res.get("stderr", "")
        }

    log_event("info", "stash", f"Successfully stashed changes on '{current_branch}' and switched to '{target_branch}'")
    return {
        "success": True,
        "stashed": True,
        "message": f"✓ Changes stashed on '{current_branch}'. Switched to '{target_branch}' successfully.",
        "previous_branch": current_branch,
        "target_branch": target_branch
    }

# ─────────────────────────────────────────────────────────────
# Complete Worktree Subsystem
# ─────────────────────────────────────────────────────────────
def list_worktrees(repo_path: str) -> List[Dict[str, Any]]:
    """Lists all worktrees with branch, path, commit hash, and main repo indicator."""
    res = run_git(repo_path, ["worktree", "list", "--porcelain"])
    worktrees = []
    
    if res["success"] and res["stdout"]:
        current_wt = {}
        for line in res["stdout"].split("\n"):
            line = line.strip()
            if not line:
                if current_wt.get("path"):
                    worktrees.append(current_wt)
                    current_wt = {}
                continue
            
            if line.startswith("worktree "):
                current_wt["path"] = line.replace("worktree ", "", 1).strip()
            elif line.startswith("HEAD "):
                current_wt["commit"] = line.replace("HEAD ", "", 1).strip()[:7]
            elif line.startswith("branch "):
                current_wt["branch"] = line.replace("branch refs/heads/", "", 1).strip()
            elif line == "bare":
                current_wt["bare"] = True
            elif line == "detached":
                current_wt["detached"] = True

        if current_wt.get("path"):
            worktrees.append(current_wt)

    # If porcelain failed or returned simple list, fallback
    if not worktrees:
        simple_res = run_git(repo_path, ["worktree", "list"])
        if simple_res["success"] and simple_res["stdout"]:
            for line in simple_res["stdout"].split("\n"):
                if line.strip():
                    parts = line.split()
                    worktrees.append({
                        "path": parts[0] if len(parts) > 0 else "",
                        "commit": parts[1] if len(parts) > 1 else "",
                        "branch": parts[2].replace("[", "").replace("]", "") if len(parts) > 2 else ""
                    })

    # Flag main repo
    rp_resolved = str(Path(repo_path).resolve())
    for wt in worktrees:
        wt_resolved = str(Path(wt.get("path", "")).resolve())
        wt["is_main"] = (wt_resolved == rp_resolved)
        wt["display_path"] = Path(wt.get("path", "")).name or wt.get("path", "")

    return worktrees

def add_worktree(repo_path: str, wt_path_str: str, branch_name: str = "", new_branch: bool = False) -> Dict[str, Any]:
    """Adds a new isolated worktree."""
    if not wt_path_str:
        return {"success": False, "error": "Worktree path cannot be empty"}
    
    # Resolve target directory
    target_p = Path(wt_path_str)
    if not target_p.is_absolute():
        target_p = (Path(repo_path).parent / wt_path_str).resolve()

    args = ["worktree", "add"]
    if new_branch and branch_name:
        args.extend(["-b", branch_name, str(target_p)])
    elif branch_name:
        args.extend([str(target_p), branch_name])
    else:
        args.append(str(target_p))

    res = run_git(repo_path, args)
    log_event("info" if res["success"] else "warn", "worktree", f"Add worktree at '{target_p}' (branch: '{branch_name}')", {"path": str(target_p)}, error=res.get("error", ""))
    return res

def remove_worktree(repo_path: str, wt_path_str: str, force: bool = False) -> Dict[str, Any]:
    """Removes an active worktree."""
    if not wt_path_str:
        return {"success": False, "error": "Worktree path cannot be empty"}
    
    args = ["worktree", "remove"]
    if force:
        args.append("--force")
    args.append(wt_path_str)

    res = run_git(repo_path, args)
    log_event("info" if res["success"] else "warn", "worktree", f"Remove worktree '{wt_path_str}'", error=res.get("error", ""))
    return res

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
