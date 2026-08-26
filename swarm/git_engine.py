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
import shutil
import json
import re
import ast
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
                "stdout": res.stdout.rstrip(),
                "stderr": res.stderr.rstrip(),
                "returncode": res.returncode
            }
        else:
            log_event("warn", "git", f"git {' '.join(args)} failed (code {res.returncode})", details, error=res.stderr.strip())
            return {
                "success": False,
                "stdout": res.stdout.rstrip(),
                "stderr": res.stderr.rstrip(),
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

def git_status_detailed(repo_path: str) -> Dict[str, Any]:
    """Returns granular git status: staged, unstaged, untracked, ahead, behind, current branch."""
    if not repo_path or not (Path(repo_path) / ".git").exists():
        return {
            "current_branch": "",
            "ahead": 0,
            "behind": 0,
            "clean": True,
            "staged": [],
            "unstaged": [],
            "untracked": [],
            "all_changes": []
        }

    branch_res = run_git(repo_path, ["branch", "--show-current"])
    current_branch = branch_res["stdout"] or "HEAD"

    ahead, behind = 0, 0
    upstream = run_git(repo_path, ["rev-parse", "--abbrev-ref", "@{u}"])
    if upstream["success"] and upstream["stdout"]:
        counts = run_git(repo_path, ["rev-list", "--left-right", "--count", f"{current_branch}...{upstream['stdout']}"])
        if counts["success"] and counts["stdout"]:
            parts = counts["stdout"].split()
            if len(parts) >= 2:
                ahead = int(parts[0])
                behind = int(parts[1])

    status_res = run_git(repo_path, ["status", "--porcelain=v1", "-uall"])
    staged = []
    unstaged = []
    untracked = []
    all_changes = []

    if status_res["success"] and status_res["stdout"]:
        for line in status_res["stdout"].split("\n"):
            if len(line) < 3:
                continue
            x = line[0]  # Staged index status
            y = line[1]  # Working tree status
            file_name = line[3:].strip()
            if " -> " in file_name:
                file_name = file_name.split(" -> ")[1].strip()

            if x == '?' and y == '?':
                item = {"path": file_name, "status": "?", "staged": False, "type": "untracked"}
                untracked.append(item)
                all_changes.append(item)
            else:
                if x != ' ':
                    status_map = {'M': 'M', 'A': 'A', 'D': 'D', 'R': 'R', 'C': 'C', 'U': 'U'}
                    staged_status = status_map.get(x, 'M')
                    item = {"path": file_name, "status": staged_status, "staged": True, "type": "staged"}
                    staged.append(item)
                    all_changes.append(item)
                if y != ' ':
                    status_map = {'M': 'M', 'A': 'A', 'D': 'D', 'R': 'R', 'C': 'C', 'U': 'U'}
                    unstaged_status = status_map.get(y, 'M')
                    item = {"path": file_name, "status": unstaged_status, "staged": False, "type": "unstaged"}
                    unstaged.append(item)
                    if x == ' ':
                        all_changes.append(item)

    return {
        "current_branch": current_branch,
        "ahead": ahead,
        "behind": behind,
        "clean": len(all_changes) == 0,
        "staged": staged,
        "unstaged": unstaged,
        "untracked": untracked,
        "all_changes": all_changes
    }

def git_stage_files(repo_path: str, files: Optional[List[str]] = None) -> Dict[str, Any]:
    """Stages specific files or all changes."""
    if not repo_path or not (Path(repo_path) / ".git").exists():
        return {"success": False, "error": "Invalid repository"}
    if not files or "." in files or "*" in files:
        res = run_git(repo_path, ["add", "-A"])
    else:
        valid_files = [f for f in files if f]
        res = run_git(repo_path, ["add", "--"] + valid_files)
    log_event("info" if res["success"] else "warn", "git", f"Stage files: {files if files else 'all'}", error=res.get("error"))
    return res

def git_unstage_files(repo_path: str, files: Optional[List[str]] = None) -> Dict[str, Any]:
    """Unstages specific files or all staged changes."""
    if not repo_path or not (Path(repo_path) / ".git").exists():
        return {"success": False, "error": "Invalid repository"}
    if not files or "." in files or "*" in files:
        res = run_git(repo_path, ["restore", "--staged", "."])
        if not res["success"]:
            res = run_git(repo_path, ["reset", "HEAD", "."])
    else:
        valid_files = [f for f in files if f]
        res = run_git(repo_path, ["restore", "--staged", "--"] + valid_files)
        if not res["success"]:
            res = run_git(repo_path, ["reset", "HEAD", "--"] + valid_files)
    log_event("info" if res["success"] else "warn", "git", f"Unstage files: {files if files else 'all'}", error=res.get("error"))
    return res

def git_discard_changes(repo_path: str, files: Optional[List[str]] = None) -> Dict[str, Any]:
    """Discards working tree modifications or removes untracked files safely."""
    if not repo_path or not (Path(repo_path) / ".git").exists():
        return {"success": False, "error": "Invalid repository"}

    rp = Path(repo_path)
    if not files or "." in files or "*" in files:
        run_git(repo_path, ["restore", "--staged", "."])
        run_git(repo_path, ["restore", "."])
        run_git(repo_path, ["clean", "-fd"])
        log_event("info", "git", "Discarded all changes in repository")
        return {"success": True, "message": "All changes discarded"}

    errors = []
    for f in files:
        if not f:
            continue
        fp = rp / f
        stat = run_git(repo_path, ["status", "--porcelain", f])
        if "??" in stat.get("stdout", "") or (fp.exists() and not stat.get("stdout", "").strip()):
            try:
                if fp.is_dir() and not fp.is_symlink():
                    shutil.rmtree(fp, ignore_errors=True)
                elif fp.exists():
                    fp.unlink(missing_ok=True)
            except Exception as e:
                errors.append(f"Failed to remove untracked {f}: {e}")
        else:
            run_git(repo_path, ["restore", "--staged", "--", f])
            res = run_git(repo_path, ["restore", "--", f])
            if not res["success"]:
                res2 = run_git(repo_path, ["checkout", "HEAD", "--", f])
                if not res2["success"]:
                    errors.append(res2.get("error", f"Failed to restore {f}"))

    if errors:
        return {"success": False, "error": "; ".join(errors)}
    return {"success": True, "message": f"Discarded changes for {len(files)} file(s)"}

def git_commit_staged(repo_path: str, summary: str, description: str = "", author_name: str = "Swarm AI Studio", author_email: str = "swarm@ai.studio") -> Dict[str, Any]:
    """Commits staged changes with explicit summary and description."""
    if not repo_path or not (Path(repo_path) / ".git").exists():
        return {"success": False, "error": "Invalid repository", "committed": False}

    summary = (summary or "").strip()
    if not summary:
        return {"success": False, "error": "Commit summary cannot be empty", "committed": False}

    full_message = f"{summary}\n\n{description.strip()}" if description and description.strip() else summary

    status_res = run_git(repo_path, ["diff", "--cached", "--name-only"])
    if not status_res["stdout"].strip():
        stat = run_git(repo_path, ["status", "--porcelain"])
        if not stat["stdout"].strip():
            head_hash = run_git(repo_path, ["rev-parse", "HEAD"])["stdout"] or ""
            return {
                "success": True,
                "committed": False,
                "message": "Working directory clean, no changes to commit",
                "commit_hash": head_hash,
                "short_hash": head_hash[:7],
                "files_changed": 0
            }
        run_git(repo_path, ["add", "-A"])
        status_res = run_git(repo_path, ["diff", "--cached", "--name-only"])

    commit_args = [
        "-c", f"user.name={author_name}",
        "-c", f"user.email={author_email}",
        "commit",
        "-m", full_message
    ]
    res = run_git(repo_path, commit_args)
    if not res["success"]:
        return {"success": False, "error": f"Git commit failed: {res.get('error')}", "committed": False}

    head_hash = run_git(repo_path, ["rev-parse", "HEAD"])["stdout"] or ""
    short_hash = run_git(repo_path, ["rev-parse", "--short", "HEAD"])["stdout"] or head_hash[:7]
    changed_count = len(status_res["stdout"].strip().splitlines()) if status_res["stdout"].strip() else 1

    log_event("info", "git", f"Created commit {short_hash}: '{summary[:60]}'", {"commit_hash": head_hash})
    return {
        "success": True,
        "committed": True,
        "commit_hash": head_hash,
        "short_hash": short_hash,
        "summary": summary,
        "description": description,
        "message": full_message,
        "files_changed": changed_count
    }

def git_fetch_remote(repo_path: str) -> Dict[str, Any]:
    """Fetches all remotes with prune."""
    res = run_git(repo_path, ["fetch", "--all", "--prune"])
    log_event("info" if res["success"] else "warn", "git", "Fetch all remotes", error=res.get("error"))
    return res

def git_pull_remote(repo_path: str, rebase: bool = False) -> Dict[str, Any]:
    """Pulls changes from upstream remote."""
    args = ["pull"]
    if rebase:
        args.append("--rebase")
    res = run_git(repo_path, args)
    log_event("info" if res["success"] else "warn", "git", f"Pull remote (rebase={rebase})", error=res.get("error"))
    return res

def git_push_remote(repo_path: str, branch: str = "", force: bool = False, set_upstream: bool = False) -> Dict[str, Any]:
    """Pushes local commits to remote tracking branch."""
    args = ["push"]
    if force:
        args.append("--force")
    if set_upstream and branch:
        args.extend(["-u", "origin", branch])
    elif branch:
        args.extend(["origin", branch])

    res = run_git(repo_path, args)
    if not res["success"] and "no upstream branch" in res.get("stderr", "").lower():
        curr_b = branch or run_git(repo_path, ["branch", "--show-current"])["stdout"]
        if curr_b:
            res = run_git(repo_path, ["push", "--set-upstream", "origin", curr_b])

    log_event("info" if res["success"] else "warn", "git", f"Push remote (branch={branch})", error=res.get("error"))
    return res

def get_full_github_desktop_state(repo_path: str) -> Dict[str, Any]:
    if not repo_path or not (Path(repo_path) / ".git").exists():
        return {"active": False}

    status_data = git_status_detailed(repo_path)
    branch = status_data["current_branch"]
    ahead = status_data["ahead"]
    behind = status_data["behind"]
    staged = status_data["staged"]
    unstaged = status_data["unstaged"]
    untracked = status_data["untracked"]
    changed_files = status_data["all_changes"]

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
    branches = git_list_branches_detailed(repo_path)

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
        "staged": staged,
        "unstaged": unstaged,
        "untracked": untracked,
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

def git_list_branches_detailed(repo_path: str) -> List[Dict[str, Any]]:
    """Returns unique, clean branch names separating local and remote branches with commit metadata."""
    fmt = "%(refname:short)|%(upstream:short)|%(HEAD)|%(objectname:short)|%(committerdate:relative)|%(subject)"
    res = run_git(repo_path, ["branch", "-a", f"--format={fmt}"])
    branches = []
    seen = set()

    if res["success"] and res["stdout"]:
        for line in res["stdout"].split("\n"):
            if not line.strip():
                continue
            parts = line.strip().split("|")
            ref_name = parts[0].strip() if len(parts) > 0 else ""
            upstream = parts[1].strip() if len(parts) > 1 else ""
            is_head = len(parts) > 2 and parts[2].strip() == "*"
            short_sha = parts[3].strip() if len(parts) > 3 else ""
            date_rel = parts[4].strip() if len(parts) > 4 else ""
            subject = parts[5].strip() if len(parts) > 5 else ""

            is_remote = False
            clean_name = ref_name
            if clean_name.startswith("origin/"):
                clean_name = clean_name.replace("origin/", "", 1)
                is_remote = True
            elif clean_name.startswith("remotes/origin/"):
                clean_name = clean_name.replace("remotes/origin/", "", 1)
                is_remote = True

            if clean_name and clean_name != "HEAD" and (clean_name, is_remote) not in seen:
                branches.append({
                    "name": clean_name,
                    "ref": ref_name,
                    "is_current": is_head,
                    "is_remote": is_remote,
                    "commit": short_sha,
                    "date": date_rel,
                    "subject": subject,
                    "upstream": upstream
                })
                seen.add((clean_name, is_remote))

    if not branches:
        branches.append({
            "name": "main",
            "ref": "main",
            "is_current": True,
            "is_remote": False,
            "commit": "",
            "date": "",
            "subject": "",
            "upstream": ""
        })
    return branches

def git_checkout_branch(repo_path: str, branch: str, create_if_missing: bool = False, start_point: str = "") -> Dict[str, Any]:
    """Checkouts an existing or new branch."""
    return switch_or_create_branch(repo_path, branch, create=create_if_missing, start_point=start_point)

def git_delete_branch(repo_path: str, branch: str, force: bool = False) -> Dict[str, Any]:
    """Deletes a local branch (with optional force)."""
    if not repo_path or not branch:
        return {"success": False, "error": "Missing repository or branch name"}
    clean_b = branch.strip().replace("origin/", "").replace("remotes/origin/", "")
    flag = "-D" if force else "-d"
    res = run_git(repo_path, ["branch", flag, clean_b])
    log_event("info" if res["success"] else "warn", "git", f"Delete branch '{clean_b}' (force={force})", error=res.get("error"))
    return res

def git_merge_branch_into_current(repo_path: str, source_branch: str, message: str = "") -> Dict[str, Any]:
    """Merges source branch into currently checked-out branch."""
    if not repo_path or not source_branch:
        return {"success": False, "error": "Missing repository or source branch", "merged": False}

    clean_src = source_branch.strip().replace("origin/", "").replace("remotes/origin/", "")
    curr_b = run_git(repo_path, ["branch", "--show-current"])["stdout"] or "HEAD"

    if clean_src == curr_b:
        return {"success": False, "error": f"Cannot merge branch '{clean_src}' into itself", "merged": False}

    msg = message.strip() or f"Merge branch '{clean_src}' into {curr_b}"
    merge_args = [
        "-c", "user.name=Swarm AI Studio",
        "-c", "user.email=swarm@ai.studio",
        "merge",
        "--no-ff",
        clean_src,
        "-m", msg
    ]
    res = run_git(repo_path, merge_args)
    if res["success"]:
        merge_commit = run_git(repo_path, ["rev-parse", "HEAD"])["stdout"] or ""
        short_hash = run_git(repo_path, ["rev-parse", "--short", "HEAD"])["stdout"] or merge_commit[:7]
        log_event("info", "git", f"Merged '{clean_src}' into '{curr_b}' (Commit: {short_hash})")
        return {
            "success": True,
            "merged": True,
            "source_branch": clean_src,
            "target_branch": curr_b,
            "merge_commit": merge_commit,
            "short_hash": short_hash
        }
    return {
        "success": False,
        "merged": False,
        "error": res.get("error") or res.get("stderr"),
        "stderr": res.get("stderr")
    }

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

def git_stash_ops(repo_path: str, op: str, message: str = "", index: int = 0, target_branch: str = "", create: bool = False) -> Dict[str, Any]:
    """Unified dispatcher for stash operations."""
    op_clean = (op or "").lower().strip()
    if op_clean == "list":
        return {"success": True, "stashes": list_stashes(repo_path)}
    elif op_clean in ("save", "push"):
        return save_stash(repo_path, message=message, include_untracked=True)
    elif op_clean == "pop":
        return pop_stash(repo_path, index=index)
    elif op_clean == "apply":
        return apply_stash(repo_path, index=index)
    elif op_clean == "drop":
        return drop_stash(repo_path, index=index)
    elif op_clean == "stash_and_switch":
        return stash_and_switch_branch(repo_path, target_branch=target_branch, create=create)
    else:
        return {"success": False, "error": f"Unknown stash operation: '{op}'"}

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

def git_file_diff(repo_path: str, file_path: str, staged: bool = False, commit_hash: str = "") -> str:
    """Gets diff for a specific file (working tree, staged, or specific commit)."""
    return get_file_diff(repo_path, file_path, staged=staged, commit_hash=commit_hash)

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

def git_commit_diff(repo_path: str, commit_sha: str) -> Dict[str, Any]:
    """Gets detailed diff and affected file list for a specific commit."""
    return get_commit_diff(repo_path, commit_sha)

def git_commit_history_detailed(repo_path: str, limit: int = 50) -> List[Dict[str, Any]]:
    """Returns formatted commit history with SHA, author, relative date, subject, and body."""
    if not repo_path or not (Path(repo_path) / ".git").exists():
        return []

    fmt = "%H%x1f%h%x1f%an%x1f%ae%x1f%ad%x1f%ar%x1f%s"
    res = run_git(repo_path, ["log", f"-n{limit}", f"--pretty=format:{fmt}"])
    commits = []

    if res["success"] and res["stdout"]:
        for line in res["stdout"].split("\n"):
            if not line.strip():
                continue
            parts = line.split("\x1f")
            if len(parts) >= 7:
                commits.append({
                    "hash": parts[0].strip(),
                    "short_hash": parts[1].strip(),
                    "author": parts[2].strip(),
                    "email": parts[3].strip(),
                    "date": parts[4].strip(),
                    "relative_date": parts[5].strip(),
                    "subject": parts[6].strip()
                })
    return commits

def git_revert_commit(repo_path: str, commit_sha: str) -> Dict[str, Any]:
    """Reverts a commit by creating a new inverse commit."""
    if not repo_path or not commit_sha:
        return {"success": False, "error": "Missing commit SHA"}
    res = run_git(repo_path, ["revert", "--no-edit", commit_sha])
    log_event("info" if res["success"] else "warn", "git", f"Revert commit {commit_sha}", error=res.get("error"))
    return res

def git_reset_commit(repo_path: str, commit_sha: str, mode: str = "soft") -> Dict[str, Any]:
    """Resets HEAD to a commit (soft, mixed, or hard)."""
    if not repo_path or not commit_sha:
        return {"success": False, "error": "Missing commit SHA"}
    valid_modes = {"soft": "--soft", "hard": "--hard", "mixed": "--mixed"}
    flag = valid_modes.get(mode.lower(), "--soft")
    res = run_git(repo_path, ["reset", flag, commit_sha])
    log_event("info" if res["success"] else "warn", "git", f"Reset to commit {commit_sha} ({flag})", error=res.get("error"))
    return res

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

def is_gh_available() -> bool:
    """Checks if GitHub CLI (gh) is available on the system PATH."""
    return shutil.which("gh") is not None

def gh_issue_create(repo_path: str, title: str, body: str, labels: Optional[List[str]] = None) -> Dict[str, Any]:
    """Creates a GitHub issue with graceful offline/local fallback."""
    if not is_gh_available() or not repo_path:
        local_id = int(time.time() % 100000)
        url = f"local://issue/{local_id}"
        log_event("info", "git", f"[Local Fallback] Created issue #{local_id}: '{title}'")
        return {"success": True, "issue_number": local_id, "url": url, "title": title, "fallback": True}

    cmd = ["gh", "issue", "create", "--title", title, "--body", body]
    if labels:
        cmd.extend(["--label", ",".join(labels)])

    try:
        res = subprocess.run(cmd, cwd=repo_path, capture_output=True, text=True, timeout=15)
        if res.returncode == 0 and res.stdout.strip():
            url = res.stdout.strip()
            match = re.search(r'/issues/(\d+)', url)
            issue_num = int(match.group(1)) if match else int(time.time() % 100000)
            log_event("info", "git", f"Created GitHub Issue #{issue_num}: '{title}' ({url})")
            return {"success": True, "issue_number": issue_num, "url": url, "title": title, "fallback": False}
        else:
            local_id = int(time.time() % 100000)
            url = f"local://issue/{local_id}"
            log_event("warn", "git", f"gh issue create returned code {res.returncode}. Using local tracking.")
            return {"success": True, "issue_number": local_id, "url": url, "title": title, "fallback": True, "error": res.stderr.strip()}
    except Exception as e:
        local_id = int(time.time() % 100000)
        url = f"local://issue/{local_id}"
        log_event("warn", "git", f"Exception running gh issue create: {e}. Using local tracking.")
        return {"success": True, "issue_number": local_id, "url": url, "title": title, "fallback": True, "error": str(e)}

def gh_issue_comment(repo_path: str, issue_number: int | str, comment: str) -> Dict[str, Any]:
    """Posts a progress comment to a GitHub issue with fallback."""
    if not is_gh_available() or not repo_path or str(issue_number).startswith("local"):
        log_event("info", "git", f"[Local Fallback] Commented on issue #{issue_number}")
        return {"success": True, "issue_number": issue_number, "commented": True, "fallback": True}

    cmd = ["gh", "issue", "comment", str(issue_number), "--body", comment]
    try:
        res = subprocess.run(cmd, cwd=repo_path, capture_output=True, text=True, timeout=15)
        if res.returncode == 0:
            log_event("info", "git", f"Commented on GitHub Issue #{issue_number}")
            return {"success": True, "issue_number": issue_number, "commented": True, "fallback": False}
        else:
            log_event("warn", "git", f"gh issue comment failed (code {res.returncode}). Fallback recorded.")
            return {"success": True, "issue_number": issue_number, "commented": True, "fallback": True}
    except Exception as e:
        log_event("warn", "git", f"Exception posting issue comment: {e}")
        return {"success": True, "issue_number": issue_number, "commented": True, "fallback": True}

def gh_issue_close(repo_path: str, issue_number: int | str, comment: str = "", reason: str = "completed") -> Dict[str, Any]:
    """Closes a GitHub issue with verification evidence."""
    if not is_gh_available() or not repo_path or str(issue_number).startswith("local"):
        log_event("info", "git", f"[Local Fallback] Closed issue #{issue_number} (reason: {reason})")
        return {"success": True, "issue_number": issue_number, "closed": True, "reason": reason, "fallback": True}

    cmd = ["gh", "issue", "close", str(issue_number), "--reason", reason]
    if comment:
        cmd.extend(["--comment", comment])

    try:
        res = subprocess.run(cmd, cwd=repo_path, capture_output=True, text=True, timeout=15)
        if res.returncode == 0:
            log_event("info", "git", f"Closed GitHub Issue #{issue_number} (reason: {reason})")
            return {"success": True, "issue_number": issue_number, "closed": True, "reason": reason, "fallback": False}
        else:
            log_event("warn", "git", f"gh issue close failed (code {res.returncode}). Fallback recorded.")
            return {"success": True, "issue_number": issue_number, "closed": True, "reason": reason, "fallback": True}
    except Exception as e:
        log_event("warn", "git", f"Exception closing issue: {e}")
        return {"success": True, "issue_number": issue_number, "closed": True, "reason": reason, "fallback": True}

def gh_issue_reopen(repo_path: str, issue_number: int | str, comment: str = "") -> Dict[str, Any]:
    """Reopens a closed GitHub issue."""
    if not is_gh_available() or not repo_path or str(issue_number).startswith("local"):
        log_event("info", "git", f"[Local Fallback] Reopened issue #{issue_number}")
        return {"success": True, "issue_number": issue_number, "reopened": True, "status": "open", "fallback": True}

    if comment.strip():
        gh_issue_comment(repo_path, issue_number, comment)

    cmd = ["gh", "issue", "reopen", str(issue_number)]
    try:
        res = subprocess.run(cmd, cwd=repo_path, capture_output=True, text=True, timeout=15)
        if res.returncode == 0:
            log_event("info", "git", f"Reopened GitHub Issue #{issue_number}")
            return {"success": True, "issue_number": issue_number, "reopened": True, "status": "open", "fallback": False}
        else:
            return {"success": True, "issue_number": issue_number, "reopened": True, "status": "open", "fallback": True}
    except Exception as e:
        log_event("warn", "git", f"Exception reopening issue: {e}")
        return {"success": True, "issue_number": issue_number, "reopened": True, "status": "open", "fallback": True}

def gh_issue_list(repo_path: str, state: str = "open") -> Dict[str, Any]:
    """Lists issues in the GitHub repository."""
    if not is_gh_available() or not repo_path:
        return {"success": True, "issues": [], "fallback": True}

    cmd = ["gh", "issue", "list", "--state", state, "--json", "number,title,state,url,createdAt"]
    try:
        res = subprocess.run(cmd, cwd=repo_path, capture_output=True, text=True, timeout=15)
        if res.returncode == 0 and res.stdout.strip():
            issues = json.loads(res.stdout.strip())
            return {"success": True, "issues": issues, "fallback": False}
        return {"success": True, "issues": [], "fallback": True}
    except Exception as e:
        return {"success": True, "issues": [], "fallback": True, "error": str(e)}

# ──────────────────────────────────────────────────────────────────────────────
# GitHub Projects (v2) Board Integration — decompose a loop goal onto a board.
# Requires the `project` token scope. When it's missing we degrade gracefully:
# every helper returns {"available": False, "reason": ...} and the caller keeps
# running (the board is a bonus, never a hard dependency).
# ──────────────────────────────────────────────────────────────────────────────

def gh_project_scope_ok() -> bool:
    """True if the gh token carries the `project` scope needed for Projects v2 writes."""
    if not is_gh_available():
        return False
    try:
        res = subprocess.run(["gh", "auth", "status"], capture_output=True, text=True, timeout=8)
        blob = (res.stdout + res.stderr)
        line = next((l for l in blob.splitlines() if "Token scopes" in l), "")
        return "'project'" in line
    except Exception:
        return False


def gh_current_owner(repo_path: str) -> Optional[str]:
    """Resolve the owner (login) of the repo's GitHub remote, for `gh project --owner`."""
    if not is_gh_available() or not repo_path:
        return None
    try:
        res = subprocess.run(
            ["gh", "repo", "view", "--json", "owner", "-q", ".owner.login"],
            cwd=repo_path, capture_output=True, text=True, timeout=10,
        )
        owner = res.stdout.strip()
        return owner or None
    except Exception:
        return None


def gh_project_ensure(repo_path: str, title: str) -> Dict[str, Any]:
    """Create (or return) a Projects v2 board for this goal. No-op without scope."""
    if not gh_project_scope_ok():
        return {"available": False, "reason": "missing 'project' token scope (run: gh auth refresh -s project)"}
    owner = gh_current_owner(repo_path)
    if not owner:
        return {"available": False, "reason": "could not resolve GitHub repo owner"}
    try:
        res = subprocess.run(
            ["gh", "project", "create", "--owner", owner, "--title", title, "--format", "json"],
            cwd=repo_path, capture_output=True, text=True, timeout=20,
        )
        if res.returncode == 0 and res.stdout.strip():
            data = json.loads(res.stdout.strip())
            num = data.get("number")
            log_event("info", "git", f"Created GitHub Project board #{num}: '{title}'")
            return {"available": True, "owner": owner, "number": num, "url": data.get("url", ""), "title": title}
        return {"available": False, "reason": (res.stderr.strip() or "gh project create failed")}
    except Exception as e:
        return {"available": False, "reason": str(e)}


def gh_project_add_issue(repo_path: str, owner: str, number: int, issue_url: str) -> Dict[str, Any]:
    """Add an existing issue/PR (by URL) to the board."""
    if not gh_project_scope_ok() or not owner or not number or not issue_url or str(issue_url).startswith("local://"):
        return {"success": False}
    try:
        res = subprocess.run(
            ["gh", "project", "item-add", str(number), "--owner", owner, "--url", issue_url, "--format", "json"],
            cwd=repo_path, capture_output=True, text=True, timeout=20,
        )
        ok = res.returncode == 0
        return {"success": ok, "error": (None if ok else res.stderr.strip())}
    except Exception as e:
        return {"success": False, "error": str(e)}


def gh_project_add_task(repo_path: str, owner: str, number: int, title: str, body: str = "") -> Dict[str, Any]:
    """Add one decomposed task as a draft item on the board; returns its item id."""
    if not gh_project_scope_ok() or not owner or not number:
        return {"success": False, "item_id": ""}
    try:
        cmd = ["gh", "project", "item-create", str(number), "--owner", owner, "--title", title, "--format", "json"]
        if body:
            cmd.extend(["--body", body[:400]])
        res = subprocess.run(cmd, cwd=repo_path, capture_output=True, text=True, timeout=20)
        if res.returncode == 0 and res.stdout.strip():
            data = json.loads(res.stdout.strip())
            return {"success": True, "item_id": data.get("id", "")}
        return {"success": False, "item_id": "", "error": res.stderr.strip()}
    except Exception as e:
        return {"success": False, "item_id": "", "error": str(e)}


def gh_project_set_status(repo_path: str, owner: str, number: int, item_id: str, status: str = "Done") -> Dict[str, Any]:
    """Best-effort: move a board item to a Status option (e.g. Done). Silent on any gap."""
    if not gh_project_scope_ok() or not owner or not number or not item_id:
        return {"success": False}
    try:
        # Resolve the project id + the "Status" single-select field and its target option id.
        proj = subprocess.run(
            ["gh", "project", "view", str(number), "--owner", owner, "--format", "json"],
            cwd=repo_path, capture_output=True, text=True, timeout=15,
        )
        project_id = json.loads(proj.stdout).get("id", "") if proj.returncode == 0 and proj.stdout.strip() else ""
        fields = subprocess.run(
            ["gh", "project", "field-list", str(number), "--owner", owner, "--format", "json"],
            cwd=repo_path, capture_output=True, text=True, timeout=15,
        )
        field_id, option_id = "", ""
        if fields.returncode == 0 and fields.stdout.strip():
            for f in json.loads(fields.stdout).get("fields", []):
                if f.get("name", "").lower() == "status":
                    field_id = f.get("id", "")
                    for opt in f.get("options", []):
                        if opt.get("name", "").lower() == status.lower():
                            option_id = opt.get("id", "")
                    break
        if not (project_id and field_id and option_id):
            return {"success": False, "reason": "Status field/option not found"}
        edit = subprocess.run(
            ["gh", "project", "item-edit", "--id", item_id, "--project-id", project_id,
             "--field-id", field_id, "--single-select-option-id", option_id],
            cwd=repo_path, capture_output=True, text=True, timeout=15,
        )
        return {"success": edit.returncode == 0}
    except Exception as e:
        return {"success": False, "error": str(e)}


def gh_pr_create(repo_path: str, title: str, body: str, base: str = "main", head: str = "") -> Dict[str, Any]:
    """Creates a pull request with graceful fallback."""
    if not is_gh_available() or not repo_path:
        local_id = int(time.time() % 100000)
        return {"success": True, "pr_number": local_id, "url": f"local://pull/{local_id}", "fallback": True}

    cmd = ["gh", "pr", "create", "--title", title, "--body", body, "--base", base]
    if head:
        cmd.extend(["--head", head])

    try:
        res = subprocess.run(cmd, cwd=repo_path, capture_output=True, text=True, timeout=20)
        if res.returncode == 0 and res.stdout.strip():
            url = res.stdout.strip()
            match = re.search(r'/pull/(\d+)', url)
            pr_num = int(match.group(1)) if match else int(time.time() % 100000)
            log_event("info", "git", f"Created GitHub PR #{pr_num}: '{title}' ({url})")
            return {"success": True, "pr_number": pr_num, "url": url, "title": title, "fallback": False}
        else:
            local_id = int(time.time() % 100000)
            return {"success": True, "pr_number": local_id, "url": f"local://pull/{local_id}", "fallback": True, "error": res.stderr.strip()}
    except Exception as e:
        local_id = int(time.time() % 100000)
        return {"success": True, "pr_number": local_id, "url": f"local://pull/{local_id}", "fallback": True, "error": str(e)}

def get_working_diff(repo_path: str, staged_only: bool = False) -> str:
    """
    Returns full unified diff of working tree changes (staged, unstaged, and untracked files).
    """
    if not repo_path or not (Path(repo_path) / ".git").exists():
        return ""
    
    diff_parts = []
    
    # 1. Staged / HEAD diff
    if staged_only:
        res_staged = run_git(repo_path, ["diff", "--cached"])
        if res_staged["success"] and res_staged["stdout"]:
            diff_parts.append(res_staged["stdout"])
    else:
        # All tracked changes vs HEAD
        res_head = run_git(repo_path, ["diff", "HEAD"])
        if res_head["success"] and res_head["stdout"]:
            diff_parts.append(res_head["stdout"])
        else:
            # Fallback if no commits yet or diff HEAD empty
            res_unstaged = run_git(repo_path, ["diff"])
            if res_unstaged["success"] and res_unstaged["stdout"]:
                diff_parts.append(res_unstaged["stdout"])
            res_staged = run_git(repo_path, ["diff", "--cached"])
            if res_staged["success"] and res_staged["stdout"]:
                diff_parts.append(res_staged["stdout"])

    # 2. Untracked files formatted as new file diffs
    status = run_git(repo_path, ["status", "--porcelain=v1", "-uall"])
    if status["success"] and status["stdout"]:
        for line in status["stdout"].splitlines():
            if line.startswith("?? "):
                file_rel = line[3:].strip()
                full_p = Path(repo_path) / file_rel
                if full_p.exists() and full_p.is_file():
                    try:
                        content = full_p.read_text(encoding="utf-8", errors="ignore")
                        lines = content.splitlines()
                        diff_parts.append(f"--- /dev/null\n+++ b/{file_rel}\n@@ -0,0 +1,{len(lines)} @@\n" + "\n".join(f"+{l}" for l in lines))
                    except Exception:
                        pass

    return "\n\n".join(diff_parts).strip()

def detect_project_test_runner(repo_path: str) -> Optional[Dict[str, Any]]:
    """
    Detects the automated test suite and runner for the repository.
    Supports Python (pytest, unittest), Node.js (npm, yarn, pnpm, bun, vitest, jest),
    Rust (cargo test), Go (go test), .NET (dotnet test), and Make (make test).
    """
    if not repo_path:
        return None
    p = Path(repo_path)
    if not p.exists():
        return None

    # 1. Python Detection
    pyproject = p / "pyproject.toml"
    pytest_ini = p / "pytest.ini"
    setup_cfg = p / "setup.cfg"
    tests_dir = p / "tests"
    test_dir = p / "test"
    
    has_py_tests = False
    if tests_dir.exists() or test_dir.exists():
        has_py_tests = True
    else:
        for root, _, files in os.walk(str(p)):
            if any(d in root for d in [".git", "node_modules", ".venv", "venv", "__pycache__", "build", "dist"]):
                continue
            if any(f.startswith("test_") or f.endswith("_test.py") for f in files if f.endswith(".py")):
                has_py_tests = True
                break

    if pyproject.exists() or pytest_ini.exists() or setup_cfg.exists() or has_py_tests:
        if shutil.which("pytest"):
            return {
                "runner": "pytest",
                "command": ["pytest"],
                "name": "pytest"
            }
        else:
            return {
                "runner": "python_unittest",
                "command": ["python3", "-m", "unittest", "discover", "tests" if tests_dir.exists() else "."],
                "name": "unittest"
            }

    # 2. Node / JS / TS Detection
    pkg_json = p / "package.json"
    if pkg_json.exists():
        try:
            pkg_data = json.loads(pkg_json.read_text(encoding="utf-8", errors="ignore"))
            scripts = pkg_data.get("scripts", {})
            if "test" in scripts:
                if (p / "pnpm-lock.yaml").exists() and shutil.which("pnpm"):
                    return {"runner": "pnpm", "command": ["pnpm", "test"], "name": "pnpm test"}
                elif (p / "yarn.lock").exists() and shutil.which("yarn"):
                    return {"runner": "yarn", "command": ["yarn", "test"], "name": "yarn test"}
                elif ((p / "bun.lockb").exists() or (p / "bun.lock").exists()) and shutil.which("bun"):
                    return {"runner": "bun", "command": ["bun", "test"], "name": "bun test"}
                else:
                    return {"runner": "npm", "command": ["npm", "test"], "name": "npm test"}
        except Exception:
            pass

    # 3. Rust Detection
    if (p / "Cargo.toml").exists() and shutil.which("cargo"):
        return {"runner": "cargo", "command": ["cargo", "test"], "name": "cargo test"}

    # 4. Go Detection
    if (p / "go.mod").exists() and shutil.which("go"):
        return {"runner": "go", "command": ["go", "test", "./..."], "name": "go test"}

    # 5. .NET Detection
    if any(p.glob("*.sln")) or any(p.glob("*.csproj")):
        if shutil.which("dotnet"):
            return {"runner": "dotnet", "command": ["dotnet", "test"], "name": "dotnet test"}

    # 6. Makefile Detection
    makefile = p / "Makefile"
    if makefile.exists():
        try:
            if "test:" in makefile.read_text(encoding="utf-8", errors="ignore"):
                return {"runner": "make", "command": ["make", "test"], "name": "make test"}
        except Exception:
            pass

    return None

def run_test_suite(repo_path: str, custom_cmd: Optional[List[str]] = None, timeout: int = 60) -> Dict[str, Any]:
    """
    Executes the real project test suite via subprocess, capturing exit code, stdout, stderr, and tracebacks.
    """
    if not repo_path:
        return {
            "success": True,
            "skipped": True,
            "exit_code": 0,
            "stdout": "",
            "stderr": "",
            "output": "No repository path provided. Tests skipped.",
            "runner": "none",
            "duration_ms": 0.0
        }

    rp = Path(repo_path)
    if not rp.exists():
        return {
            "success": False,
            "skipped": False,
            "exit_code": 1,
            "stdout": "",
            "stderr": f"Path does not exist: {repo_path}",
            "output": f"Path does not exist: {repo_path}",
            "runner": "none",
            "duration_ms": 0.0,
            "error": f"Path does not exist: {repo_path}"
        }

    runner_info = None
    if custom_cmd:
        cmd = custom_cmd
        runner_name = "custom"
    else:
        runner_info = detect_project_test_runner(repo_path)
        if not runner_info:
            return {
                "success": True,
                "skipped": True,
                "exit_code": 0,
                "stdout": "No automated test suite detected.",
                "stderr": "",
                "output": "No automated test runner detected in repository.",
                "runner": "none",
                "duration_ms": 0.0
            }
        cmd = runner_info["command"]
        runner_name = runner_info.get("name", runner_info.get("runner", "unknown"))

    t0 = time.time()
    try:
        res = subprocess.run(cmd, cwd=str(rp), capture_output=True, text=True, timeout=timeout)
        duration_ms = round((time.time() - t0) * 1000, 1)
        full_out = (res.stdout.strip() + "\n" + res.stderr.strip()).strip()

        if res.returncode == 0:
            log_event("info", "test_runner", f"Tests passed ({runner_name}) took {duration_ms}ms", {"cmd": " ".join(cmd), "duration_ms": duration_ms})
            return {
                "success": True,
                "skipped": False,
                "exit_code": 0,
                "stdout": res.stdout.strip(),
                "stderr": res.stderr.strip(),
                "output": full_out,
                "runner": runner_name,
                "duration_ms": duration_ms
            }
        else:
            log_event("warn", "test_runner", f"Tests failed ({runner_name}) code {res.returncode}", {"cmd": " ".join(cmd), "duration_ms": duration_ms, "error": res.stderr.strip()[:200]})
            return {
                "success": False,
                "skipped": False,
                "exit_code": res.returncode,
                "stdout": res.stdout.strip(),
                "stderr": res.stderr.strip(),
                "output": full_out,
                "runner": runner_name,
                "duration_ms": duration_ms,
                "error": res.stderr.strip() or res.stdout.strip() or f"Test command failed with code {res.returncode}"
            }
    except subprocess.TimeoutExpired:
        duration_ms = round((time.time() - t0) * 1000, 1)
        err_msg = f"Test execution timed out after {timeout}s"
        log_event("error", "test_runner", err_msg, {"cmd": " ".join(cmd)})
        return {
            "success": False,
            "skipped": False,
            "exit_code": 124,
            "stdout": "",
            "stderr": err_msg,
            "output": err_msg,
            "runner": runner_name,
            "duration_ms": duration_ms,
            "error": err_msg
        }
    except Exception as e:
        duration_ms = round((time.time() - t0) * 1000, 1)
        err_msg = str(e)
        log_event("error", "test_runner", f"Exception running tests ({runner_name}): {err_msg}", {"cmd": " ".join(cmd)})
        return {
            "success": False,
            "skipped": False,
            "exit_code": 1,
            "stdout": "",
            "stderr": err_msg,
            "output": err_msg,
            "runner": runner_name,
            "duration_ms": duration_ms,
            "error": err_msg
        }

def _parse_tool_call_writes(llm_output: str) -> List[Dict[str, str]]:
    """Parse the local model's native tool-call format into (path, content) pairs.

    Liquid LFM 2.5 (and similar) emit file writes as:
        <|tool_call_start|>[write(path='a.py', content='...'), write(path="b.py", content="...")]<|tool_call_end|>
    rather than markdown fences or JSON. We parse the call list with `ast` (parse
    only — never eval) and pull the path/content from write/create/edit calls.
    """
    files: List[Dict[str, str]] = []
    WRITE_FUNCS = {"write", "write_file", "create_file", "create", "edit",
                   "replace_content", "replace_file_content", "save_file"}

    # Collect candidate call-list snippets: prefer explicit tool-call blocks,
    # else fall back to any bare "[write(...)]" list in the text.
    snippets = re.findall(r'<\|tool_call_start\|>\s*(\[.*?\])\s*<\|tool_call_end\|>', llm_output, re.DOTALL)
    if not snippets:
        snippets = re.findall(r'<\|tool_call_start\|>\s*(\[.*)', llm_output, re.DOTALL)  # missing end tag
    if not snippets:
        m = re.search(r'(\[\s*(?:write|write_file|create_file|create|edit|replace_content|replace_file_content|save_file)\s*\(.*\])',
                      llm_output, re.DOTALL)
        if m:
            snippets = [m.group(1)]

    for snip in snippets:
        node = None
        for candidate in (snip, snip.rstrip().rstrip(',') + "]" if not snip.rstrip().endswith("]") else snip):
            try:
                node = ast.parse(candidate.strip(), mode="eval").body
                break
            except Exception:
                continue
        if node is None:
            continue
        calls = node.elts if isinstance(node, ast.List) else [node]
        for call in calls:
            if not isinstance(call, ast.Call):
                continue
            fname = call.func.id if isinstance(call.func, ast.Name) else getattr(call.func, "attr", "")
            if fname not in WRITE_FUNCS:
                continue
            path_val = content_val = None
            PATH_KW = ("path", "file", "filename", "filepath", "file_path", "file_name", "fpath", "target")
            CONTENT_KW = ("content", "contents", "code", "text", "body", "file_content", "data", "new_content")
            for kw in call.keywords:
                if kw.arg in PATH_KW and isinstance(kw.value, ast.Constant):
                    path_val = kw.value.value
                elif kw.arg in CONTENT_KW and isinstance(kw.value, ast.Constant):
                    content_val = kw.value.value
            # Positional fallback: write('path', 'content')
            pos = [a.value for a in call.args if isinstance(a, ast.Constant)]
            if path_val is None and len(pos) >= 1:
                path_val = pos[0]
            if content_val is None and len(pos) >= 2:
                content_val = pos[1]
            if isinstance(path_val, str) and isinstance(content_val, str):
                files.append({"path": path_val, "content": content_val})
    return files


def extract_code_blocks_and_write(repo_path: str, llm_output: str) -> List[Dict[str, Any]]:
    """
    Extracts code files from LLM output and writes them to the repository.
    Understands three formats: the local model's native tool-call syntax
    (<|tool_call_start|>[write(path=..., content=...)]<|tool_call_end|>),
    JSON patches, and Markdown code fences.
    """
    if not llm_output or not isinstance(llm_output, str):
        return []

    written_files = []
    seen_paths = set()
    rp = Path(repo_path) if repo_path else None

    def _write_single_file(rel_path_str: str, file_content: str) -> Optional[Dict[str, Any]]:
        clean_path = rel_path_str.strip().strip('"`\'')
        if clean_path.startswith("./"):
            clean_path = clean_path[2:]

        # Models often emit an ABSOLUTE path that already points inside the repo
        # (e.g. /home/.../repo/src/x.py). Rebase it to a repo-relative path rather
        # than blindly stripping the leading slash (which produced a bogus nested
        # dir and meant nothing landed). Only strip the slash for a genuinely
        # foreign absolute path, where the containment check below then rejects it.
        if clean_path.startswith("/") and rp:
            try:
                rebased = Path(clean_path).resolve().relative_to(rp.resolve())
                clean_path = str(rebased)
            except (ValueError, OSError):
                clean_path = clean_path.lstrip("/")
        elif clean_path.startswith("/"):
            clean_path = clean_path.lstrip("/")

        # Check for traversal attack
        if ".." in clean_path.split("/") or ".." in clean_path.split("\\"):
            log_event("warn", "file_writer", f"Rejected insecure file path traversal: {clean_path}")
            return None

        # Ignore obvious non-filepath strings
        if not clean_path or clean_path.lower() in [
            "json", "python", "javascript", "typescript", "bash", "sh", "yaml", "yml",
            "html", "css", "sql", "markdown", "text", "output", "example", "none"
        ]:
            return None

        if clean_path in seen_paths:
            pass
        seen_paths.add(clean_path)

        abs_path_str = ""
        if rp and rp.exists():
            target_p = (rp / clean_path).resolve()
            try:
                target_p.relative_to(rp.resolve())
            except ValueError:
                log_event("warn", "file_writer", f"Path {clean_path} resolves outside repo {repo_path}")
                return None
            try:
                target_p.parent.mkdir(parents=True, exist_ok=True)
                target_p.write_text(file_content, encoding="utf-8")
                abs_path_str = str(target_p)
                log_event("info", "file_writer", f"Wrote file '{clean_path}' ({len(file_content)} bytes)")
            except Exception as e:
                log_event("warn", "file_writer", f"Failed to write file {clean_path}: {e}")
                abs_path_str = str(target_p)
        elif rp:
            abs_path_str = str(rp / clean_path)
        else:
            abs_path_str = clean_path

        return {
            "path": clean_path,
            "abs_path": abs_path_str,
            "bytes": len(file_content),
            "lines": len(file_content.splitlines())
        }

    # 0. Native tool-call format (primary output of Liquid LFM 2.5 and peers).
    for rec in _parse_tool_call_writes(llm_output):
        w = _write_single_file(rec["path"], rec["content"])
        if w:
            written_files.append(w)
    if written_files:
        return written_files

    # 1. Attempt JSON parsing
    json_blocks = re.findall(r'```(?:json)?\s*([\[\{][\s\S]*?[\]\}])\s*```', llm_output, re.IGNORECASE)
    if not json_blocks and (llm_output.strip().startswith("[") or llm_output.strip().startswith("{")):
        json_blocks = [llm_output.strip()]

    for jb in json_blocks:
        try:
            data = json.loads(jb)
            file_items = []
            if isinstance(data, list):
                file_items = data
            elif isinstance(data, dict):
                if "files" in data and isinstance(data["files"], list):
                    file_items = data["files"]
                elif "patches" in data and isinstance(data["patches"], list):
                    file_items = data["patches"]
                elif any(k in data for k in ["path", "file", "filename"]):
                    file_items = [data]
            
            for item in file_items:
                if isinstance(item, dict):
                    p_val = item.get("path") or item.get("file") or item.get("filename")
                    c_val = item.get("content") or item.get("code") or item.get("text")
                    if p_val and c_val is not None:
                        rec = _write_single_file(str(p_val), str(c_val))
                        if rec:
                            written_files.append(rec)
        except Exception:
            pass

    if written_files:
        return written_files

    # 2. Markdown Code Fences Parser
    fence_pattern = re.compile(r'(?:^|\n)(?:`{3,}|~{3,})([^\n]*)\n([\s\S]*?)(?:`{3,}|~{3,})', re.MULTILINE)
    for match in fence_pattern.finditer(llm_output):
        info_str = match.group(1).strip()
        content = match.group(2)
        start_pos = match.start()

        target_file = ""

        # A. Info string matching
        fp_match = re.search(r'(?:filepath|filename|file)=["\']?([^"\'\s]+)["\']?', info_str, re.IGNORECASE)
        if fp_match:
            target_file = fp_match.group(1)
        elif ":" in info_str:
            parts = info_str.split(":", 1)
            candidate = parts[1].strip().strip('"`\'')
            if ("." in candidate or "/" in candidate) and not candidate.startswith("/"):
                target_file = candidate
        elif ("." in info_str or "/" in info_str) and not any(k in info_str.lower() for k in ["example", "snippet", "output"]):
            candidate = info_str.strip().strip('"`\'')
            if not candidate.startswith("```") and "." in candidate:
                target_file = candidate

        # B. Text immediately preceding code fence
        if not target_file:
            preceding_text = llm_output[:start_pos].strip()
            preceding_lines = preceding_text.splitlines()[-5:] if preceding_text else []
            preceding_chunk = "\n".join(preceding_lines)
            
            hdr_match = re.search(r'(?:###|\*\*|\*|#)?\s*(?:File|FILE|Path|PATH|Create|Update|Modifying)?\s*[:\-]?\s*[`"\'\[]([a-zA-Z0-9_\-./\\]+\.[a-zA-Z0-9]+|Makefile|Dockerfile)[`"\'\]]', preceding_chunk)
            if hdr_match:
                target_file = hdr_match.group(1)
            else:
                hdr_match2 = re.search(r'###\s+([a-zA-Z0-9_\-./\\]+\.[a-zA-Z0-9]+|Makefile|Dockerfile)', preceding_chunk)
                if hdr_match2:
                    target_file = hdr_match2.group(1)

        # C. First line comment inside code content
        if not target_file and content:
            first_line = content.splitlines()[0].strip() if content.splitlines() else ""
            in_code_match = re.search(r'^(?:#|//|/\*|--)\s*(?:filepath|filename|file)\s*[:\-]?\s*[`"\'\s]*([a-zA-Z0-9_\-./\\]+\.[a-zA-Z0-9]+|Makefile|Dockerfile)[`"\'\s]*(?:\*/)?', first_line, re.IGNORECASE)
            if in_code_match:
                target_file = in_code_match.group(1)
                content = "\n".join(content.splitlines()[1:])

        if target_file:
            rec = _write_single_file(target_file, content)
            if rec:
                written_files.append(rec)

    return written_files

def commit_changes(repo_path: str, message: str, author_name: str = "Swarm AI Studio", author_email: str = "swarm@ai.studio") -> Dict[str, Any]:
    """
    Stages all modified/untracked files and commits them with an authoritative commit message.
    """
    if not repo_path or not (Path(repo_path) / ".git").exists():
        return {"success": False, "error": "Invalid or missing git repository", "committed": False}

    # 1. Stage all changes, then unstage common build junk the test runner emits
    #    (running pytest generates __pycache__/*.pyc which `add -A` would otherwise
    #    sweep into the commit). Keeps autonomous commits clean.
    add_res = run_git(repo_path, ["add", "-A"])
    if not add_res["success"]:
        return {"success": False, "error": f"Failed to stage changes: {add_res.get('error')}", "committed": False}
    run_git(repo_path, ["reset", "-q", "--",
                        ":(glob)**/__pycache__/**", ":(glob)**/*.pyc", ":(glob)**/*.pyo",
                        ":(glob)**/.pytest_cache/**"])

    # 2. Check if there are staged changes
    status_res = run_git(repo_path, ["status", "--porcelain"])
    if not status_res["success"]:
        return {"success": False, "error": f"Failed to check git status: {status_res.get('error')}", "committed": False}

    if not status_res["stdout"].strip():
        head_hash = run_git(repo_path, ["rev-parse", "HEAD"])["stdout"] or ""
        short_hash = run_git(repo_path, ["rev-parse", "--short", "HEAD"])["stdout"] or ""
        return {
            "success": True,
            "committed": False,
            "message": "Working directory clean, no changes to commit",
            "commit_hash": head_hash,
            "short_hash": short_hash,
            "files_changed": 0
        }

    # 3. Perform git commit with explicit author config
    commit_args = [
        "-c", f"user.name={author_name}",
        "-c", f"user.email={author_email}",
        "commit",
        "-m", message.strip() or "feat: Autonomous Swarm update"
    ]
    commit_res = run_git(repo_path, commit_args)
    if not commit_res["success"]:
        return {"success": False, "error": f"Git commit failed: {commit_res.get('error')}", "committed": False}

    # 4. Get commit hash & stats
    head_hash = run_git(repo_path, ["rev-parse", "HEAD"])["stdout"] or ""
    short_hash = run_git(repo_path, ["rev-parse", "--short", "HEAD"])["stdout"] or ""
    changed_count = len(status_res["stdout"].strip().splitlines())

    log_event("info", "git", f"Created commit {short_hash}: '{message.strip()[:60]}'", {"commit_hash": head_hash, "files_changed": changed_count})
    return {
        "success": True,
        "committed": True,
        "commit_hash": head_hash,
        "short_hash": short_hash,
        "message": message,
        "files_changed": changed_count
    }

def merge_branch(repo_path: str, source_branch: str, target_branch: str = "main", message: str = "") -> Dict[str, Any]:
    """
    Merges source_branch into target_branch with authoritative logging and merge commit verification.
    """
    if not repo_path or not (Path(repo_path) / ".git").exists():
        return {"success": False, "error": "Invalid or missing git repository", "merged": False}

    if not source_branch:
        return {"success": False, "error": "Source branch cannot be empty", "merged": False}

    clean_src = source_branch.strip().replace("origin/", "").replace("remotes/origin/", "")
    clean_target = target_branch.strip().replace("origin/", "").replace("remotes/origin/", "")

    if clean_src == clean_target:
        head_hash = run_git(repo_path, ["rev-parse", "HEAD"])["stdout"] or ""
        return {
            "success": True,
            "merged": True,
            "already_on_target": True,
            "source_branch": clean_src,
            "target_branch": clean_target,
            "merge_commit": head_hash
        }

    # Verify target branch exists locally or on remote; fallback from main to master if needed
    target_check = run_git(repo_path, ["show-ref", "--verify", f"refs/heads/{clean_target}"])
    if not target_check["success"] and clean_target == "main":
        master_check = run_git(repo_path, ["show-ref", "--verify", "refs/heads/master"])
        if master_check["success"]:
            clean_target = "master"

    # Switch to target branch
    checkout_res = switch_or_create_branch(repo_path, clean_target)
    if not checkout_res["success"]:
        return {"success": False, "error": f"Failed to checkout target branch '{clean_target}': {checkout_res.get('error')}", "merged": False}

    # Merge source branch into target branch
    merge_msg = message.strip() or f"Merge branch '{clean_src}' into '{clean_target}'"
    merge_args = [
        "-c", "user.name=Swarm AI Studio",
        "-c", "user.email=swarm@ai.studio",
        "merge",
        "--no-ff",
        clean_src,
        "-m", merge_msg
    ]
    merge_res = run_git(repo_path, merge_args)
    if not merge_res["success"]:
        log_event("warn", "git", f"Failed to merge '{clean_src}' into '{clean_target}'", error=merge_res.get("error"))
        return {
            "success": False,
            "error": f"Merge failed: {merge_res.get('error')}",
            "merged": False,
            "stderr": merge_res.get("stderr", "")
        }

    merge_commit = run_git(repo_path, ["rev-parse", "HEAD"])["stdout"] or ""
    short_hash = run_git(repo_path, ["rev-parse", "--short", "HEAD"])["stdout"] or ""
    log_event("info", "git", f"Successfully merged '{clean_src}' into '{clean_target}' (Commit: {short_hash})")

    return {
        "success": True,
        "merged": True,
        "source_branch": clean_src,
        "target_branch": clean_target,
        "merge_commit": merge_commit,
        "short_hash": short_hash
    }


