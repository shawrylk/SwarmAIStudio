"""
Pi Coding Agent Bridge.

Runs a real agentic tool loop (read / edit / write / bash) for the Dev role
instead of a single blind completion.

Why this exists: `query_local_slot` issues one POST and returns one string, so
the dev model can never look at a file before rewriting it. Asked to refactor a
380-line source file it had never seen, it could only invent a short plausible
replacement — FishAI.cs went 380 -> 69 lines, GpuBoidSimulation.cs 188 -> 23,
and the harness applied every stub verbatim. Pi gives the same model a `read`
tool, which turns a blind full-file overwrite into a targeted edit.

Pi is driven headlessly via `pi --print --mode json`, which streams JSONL events
on stdout. Configuration is hermetic: PI_CODING_AGENT_DIR points at a directory
this module owns, so the user's own ~/.pi settings, auth and skills are never
read or modified.
"""

import asyncio
import json
import os
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

from swarm.config import LFM_URL, SWARM_DIR
from swarm.logger import log_event

PI_CONFIG_DIR = SWARM_DIR / "pi_config"

# Tools whose invocation means the agent changed a file on disk.
MUTATING_TOOLS = {"edit", "write", "multiedit", "multi_edit", "apply_patch", "create"}

# Startup network calls block indefinitely on an offline/slow host: a first
# attempt hung for minutes at 0% CPU without ever opening a socket to the model.
# Every invocation is forced offline.
PI_BASE_ENV = {
    "PI_OFFLINE": "1",
    "PI_SKIP_VERSION_CHECK": "1",
}


def pi_available() -> bool:
    """True if the `pi` CLI is on PATH."""
    return shutil.which("pi") is not None


def _base_url_from_lfm(lfm_url: str) -> str:
    """Derive an OpenAI-compatible base URL from the configured chat endpoint."""
    url = (lfm_url or "").strip()
    for suffix in ("/chat/completions", "/completions"):
        if url.endswith(suffix):
            return url[: -len(suffix)]
    return url.rstrip("/")


def discover_local_model(timeout: float = 5.0) -> Optional[str]:
    """Ask the local engine which model it serves, rather than hardcoding an id."""
    base = _base_url_from_lfm(LFM_URL)
    for path in ("/models", "/v1/models"):
        try:
            resp = httpx.get(f"{base}{path}", timeout=timeout)
            if resp.status_code != 200:
                continue
            data = resp.json()
            items = data.get("models") or data.get("data") or []
            for item in items:
                mid = item.get("id") or item.get("model") or item.get("name")
                if mid:
                    return str(mid)
        except Exception:
            continue
    return None


def ensure_pi_config(model_id: Optional[str] = None) -> Optional[Path]:
    """Write a self-contained Pi config pointing at the local engine.

    Returns the config directory, or None if no model could be resolved. Kept
    outside the user's ~/.pi so their provider list, credentials and skills are
    untouched.
    """
    model = model_id or discover_local_model()
    if not model:
        log_event("warn", "pi_agent", "Could not resolve a local model id; Pi bridge unavailable")
        return None

    PI_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    models = {
        "providers": {
            "swarm-local": {
                "baseUrl": _base_url_from_lfm(LFM_URL),
                "api": "openai-completions",
                "apiKey": "local",
                "compat": {
                    "supportsDeveloperRole": False,
                    "supportsReasoningEffort": False,
                },
                "models": [
                    {
                        "id": model,
                        "name": f"Swarm local ({model})",
                        "reasoning": True,
                        "input": ["text"],
                        "contextWindow": 98304,
                        "maxTokens": 16384,
                        "cost": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0},
                    }
                ],
            }
        }
    }
    settings = {
        "defaultProvider": "swarm-local",
        "defaultModel": model,
        "quietStartup": True,
    }
    (PI_CONFIG_DIR / "models.json").write_text(json.dumps(models, indent=2), encoding="utf-8")
    (PI_CONFIG_DIR / "settings.json").write_text(json.dumps(settings, indent=2), encoding="utf-8")
    return PI_CONFIG_DIR


def _relativize(path_str: str, repo_root: Path) -> Optional[str]:
    """Return a repo-relative path, or None if it escapes the repository.

    Pi reports absolute paths. Containment is enforced here because the Pi path
    bypasses extract_code_blocks_and_write, which used to perform this check.
    """
    try:
        p = Path(path_str)
        if not p.is_absolute():
            p = repo_root / p
        resolved = p.resolve()
        return str(resolved.relative_to(repo_root.resolve()))
    except (ValueError, OSError):
        return None


def parse_pi_events(stdout: str, repo_path: str) -> Dict[str, Any]:
    """Extract the final assistant text, tool calls and written files from JSONL.

    `message_update` deltas are ignored — a trivial two-step task emitted 827 of
    them (2 MB), and only the terminal `message_end` records carry final content.
    """
    repo_root = Path(repo_path) if repo_path else None
    final_text = ""
    tool_calls: List[Dict[str, Any]] = []
    written: List[str] = []
    rejected: List[str] = []

    for line in stdout.splitlines():
        line = line.strip()
        if not line or not line.startswith("{"):
            continue
        try:
            evt = json.loads(line)
        except json.JSONDecodeError:
            continue
        if evt.get("type") != "message_end":
            continue

        msg = evt.get("message") or {}
        content = msg.get("content") or []
        if msg.get("role") == "assistant":
            text = "".join(
                b.get("text", "")
                for b in content
                if isinstance(b, dict) and b.get("type") == "text"
            )
            if text.strip():
                final_text = text

        for block in content:
            if not isinstance(block, dict) or block.get("type") != "toolCall":
                continue
            name = (block.get("name") or "").lower()
            args = block.get("arguments") or {}
            tool_calls.append({"name": name, "path": args.get("path", "")})
            if name not in MUTATING_TOOLS:
                continue
            raw_path = args.get("path") or args.get("file_path") or ""
            if not raw_path or not repo_root:
                continue
            rel = _relativize(str(raw_path), repo_root)
            if rel is None:
                rejected.append(str(raw_path))
                log_event("warn", "pi_agent", f"Rejected write outside repository: {raw_path}")
            elif rel not in written:
                written.append(rel)

    return {
        "text": final_text,
        "tool_calls": tool_calls,
        "files_written": written,
        "rejected_paths": rejected,
    }


def detect_malformed_writes(repo_path: str, rel_paths: List[str]) -> List[str]:
    """Find files written with literal escape sequences instead of real newlines.

    Observed live: the agent emitted a test file whose entire body was one line
    containing the two characters backslash-n wherever a newline belonged, so
    pytest failed at collection with an unhelpful import traceback. The gate
    caught it, but the retry feedback never said why. Naming it explicitly turns
    an opaque collection error into an actionable instruction.
    """
    bad: List[str] = []
    root = Path(repo_path)
    for rel in rel_paths:
        try:
            text = (root / rel).read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if not text:
            continue
        # A source file of any size that contains no real newline but does contain
        # the literal two-character sequence is corrupt, not merely minified.
        if "\\n" in text and "\n" not in text.strip("\n") and len(text) > 120:
            bad.append(rel)
    return bad


async def run_pi_agent(
    prompt: str,
    repo_path: str,
    system: Optional[str] = None,
    timeout: float = 900.0,
    model_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Run one headless Pi session against `repo_path` and report what it changed.

    Returns success, the agent's final message, the tool calls it made, and the
    repo-relative files it actually wrote. On any failure the caller is expected
    to fall back to the single-completion path.
    """
    if not pi_available():
        return {"success": False, "error": "pi CLI not found on PATH", "files_written": [], "text": ""}
    if not repo_path or not Path(repo_path).exists():
        return {"success": False, "error": f"Invalid repo path: {repo_path}", "files_written": [], "text": ""}

    cfg = ensure_pi_config(model_id)
    if not cfg:
        return {"success": False, "error": "No local model available for Pi", "files_written": [], "text": ""}

    args = ["pi", "--print", "--mode", "json", "--approve", "--offline"]
    if system:
        args += ["--append-system-prompt", system]
    args.append(prompt)

    env = {**os.environ, **PI_BASE_ENV, "PI_CODING_AGENT_DIR": str(cfg)}

    try:
        proc = await asyncio.create_subprocess_exec(
            *args,
            cwd=repo_path,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
    except Exception as e:
        return {"success": False, "error": f"Failed to launch pi: {e}", "files_written": [], "text": ""}

    try:
        stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        try:
            proc.kill()
        except ProcessLookupError:
            pass
        log_event("warn", "pi_agent", f"Pi agent timed out after {timeout}s")
        return {
            "success": False,
            "error": f"Pi agent timed out after {timeout}s",
            "files_written": [],
            "text": "",
        }

    stdout = stdout_b.decode("utf-8", errors="ignore")
    stderr = stderr_b.decode("utf-8", errors="ignore").strip()
    parsed = parse_pi_events(stdout, repo_path)

    if proc.returncode != 0:
        log_event("warn", "pi_agent", f"Pi exited {proc.returncode}", error=stderr[:300])
        return {
            "success": False,
            "error": f"pi exited {proc.returncode}: {stderr[:300]}",
            "files_written": parsed["files_written"],
            "text": parsed["text"],
            "tool_calls": parsed["tool_calls"],
        }

    log_event(
        "info",
        "pi_agent",
        f"Pi session complete: {len(parsed['tool_calls'])} tool call(s), "
        f"{len(parsed['files_written'])} file(s) written",
        {"files": parsed["files_written"][:10]},
    )
    return {
        "success": True,
        "error": "",
        "text": parsed["text"],
        "tool_calls": parsed["tool_calls"],
        "files_written": parsed["files_written"],
        "rejected_paths": parsed["rejected_paths"],
    }
