"""
Disk Memory & File Grounding Engine for Swarm AI Studio
Reads real files from disk (repositories, .swarm/, .gemini/, .gsd/, MEMORY.md, rules)
to prevent hallucinations and ensure answers are 100% grounded in verified filesystem facts.
"""

import os
import json
from pathlib import Path
from typing import Dict, List, Any, Optional

SWARM_HOME = Path.home() / ".swarm"
GEMINI_HOME = Path.home() / ".gemini"
GSD_HOME = Path.home() / ".gsd"

def read_disk_memory_files(repo_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Reads actual memory, preferences, rules, and configuration files from disk.
    Returns structured ground-truth facts.
    """
    memory_data: Dict[str, Any] = {
        "global_rules": "",
        "preferences": "",
        "repo_memory": "",
        "recent_artifacts": [],
        "grounded_files": []
    }

    # 1. Read Global Swarm Rules (~/.swarm/global_rules.md or ~/.swarm/rules/)
    global_rules_file = SWARM_HOME / "global_rules.md"
    if global_rules_file.is_file():
        try:
            memory_data["global_rules"] = global_rules_file.read_text(encoding="utf-8", errors="ignore").strip()
            memory_data["grounded_files"].append(str(global_rules_file))
        except Exception:
            pass

    # 2. Read GSD / Pi Preferences (~/.gsd/PREFERENCES.md)
    gsd_pref_file = GSD_HOME / "PREFERENCES.md"
    if gsd_pref_file.is_file():
        try:
            content = gsd_pref_file.read_text(encoding="utf-8", errors="ignore").strip()
            memory_data["preferences"] = content[:3000]
            memory_data["grounded_files"].append(str(gsd_pref_file))
        except Exception:
            pass

    # 3. Read Repository-Specific Memory & Rules
    if repo_path and os.path.isdir(repo_path):
        rpath = Path(repo_path)
        repo_docs = []

        # 3a. Read GSD Codebase Map and Snapshots (.gsd/CODEBASE.md, .gsd/last-snapshot.md)
        gsd_dir = rpath / ".gsd"
        if gsd_dir.is_dir():
            gsd_codebase = gsd_dir / "CODEBASE.md"
            if gsd_codebase.is_file():
                try:
                    c_text = gsd_codebase.read_text(encoding="utf-8", errors="ignore").strip()
                    if c_text:
                        repo_docs.append(f"--- GSD Codebase Map (.gsd/CODEBASE.md) ---\n{c_text[:3000]}")
                        memory_data["grounded_files"].append(str(gsd_codebase))
                        memory_data["gsd_codebase_map"] = c_text[:3000]
                except Exception:
                    pass

            gsd_snapshot = gsd_dir / "last-snapshot.md"
            if gsd_snapshot.is_file():
                try:
                    s_text = gsd_snapshot.read_text(encoding="utf-8", errors="ignore").strip()
                    if s_text and "No durable memories" not in s_text:
                        repo_docs.append(f"--- GSD Context Snapshot (.gsd/last-snapshot.md) ---\n{s_text[:2000]}")
                        memory_data["grounded_files"].append(str(gsd_snapshot))
                except Exception:
                    pass
        repo_candidates = [
            rpath / "MEMORY.md",
            rpath / "ARCHITECTURE.md",
            rpath / ".cursorrules",
            rpath / "GEMINI.md",
            rpath / "CONTRIBUTING.md",
            rpath / "pyproject.toml",
            rpath / "package.json",
            rpath / "Cargo.toml",
            rpath / "go.mod"
        ]
        for cand in repo_candidates:
            if cand.is_file():
                try:
                    text = cand.read_text(encoding="utf-8", errors="ignore").strip()
                    if text:
                        repo_docs.append(f"--- File: {cand.name} ---\n{text[:2000]}")
                        memory_data["grounded_files"].append(str(cand))
                        if cand.name in ["pyproject.toml", "package.json", "Cargo.toml", "go.mod"]:
                            memory_data["manifest_config"] = text
                except Exception:
                    pass
        if repo_docs:
            memory_data["repo_memory"] = "\n\n".join(repo_docs)

        # Extract AST symbols directly from disk source files
        memory_data["ast_symbols"] = extract_ast_symbol_summary(repo_path)

    # 4. Read Recent Artifacts in ~/.swarm/artifacts/
    artifacts_dir = SWARM_HOME / "artifacts"
    if artifacts_dir.is_dir():
        try:
            files = sorted(artifacts_dir.glob("*.md"), key=lambda f: f.stat().st_mtime, reverse=True)[:5]
            for f in files:
                memory_data["recent_artifacts"].append({
                    "filename": f.name,
                    "path": str(f),
                    "summary": f.read_text(encoding="utf-8", errors="ignore")[:400]
                })
                memory_data["grounded_files"].append(str(f))
        except Exception:
            pass

    memory_data["has_disk_rules"] = bool(memory_data["global_rules"])
    memory_data["has_repo_memory"] = bool(memory_data["repo_memory"])
    if "manifest_config" not in memory_data:
        memory_data["manifest_config"] = ""
    if "ast_symbols" not in memory_data:
        memory_data["ast_symbols"] = []

    return memory_data

def format_disk_memory_prompt_block(memory_data: Dict[str, Any]) -> str:
    """Formats verified disk memory into a clean grounding prompt block."""
    blocks = ["=== VERIFIED DISK MEMORY & GROUNDED FACTS (FROM LOCAL FILESYSTEM) ==="]
    
    if memory_data.get("grounded_files"):
        blocks.append(f"Grounded Source Files: {', '.join(memory_data['grounded_files'])}")

    if memory_data.get("global_rules"):
        blocks.append(f"\n[Global Architectural Rules ({SWARM_HOME}/global_rules.md)]:\n{memory_data['global_rules']}")

    if memory_data.get("ast_symbols"):
        sym_lines = ["\n[Codebase Symbols & AST Declarations (From Disk)]:" ]
        for s in memory_data["ast_symbols"][:10]:
            sym_lines.append(f"- {s['type']} `{s['name']}` ({s.get('file', '')})")
        blocks.append("\n".join(sym_lines))

    blocks.append("=====================================================================")
    return "\n".join(blocks)

def extract_ast_symbol_summary(repo_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Extracts top-level symbols (classes, functions) directly from source files on disk using AST.
    Ensures the swarm knows exact code structure from disk without relying on fuzzy memory.
    """
    if not repo_path or not os.path.isdir(repo_path):
        return []

    symbols = []
    rpath = Path(repo_path)
    
    # Scan Python files with ast
    import ast
    for py_file in list(rpath.glob("**/*.py"))[:20]:
        if any(part.startswith(".") or part in ["venv", ".venv", "node_modules", "target"] for part in py_file.parts):
            continue
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8", errors="ignore"))
            for node in ast.iter_child_nodes(tree):
                if isinstance(node, ast.ClassDef):
                    symbols.append({
                        "name": node.name,
                        "type": "class",
                        "file": str(py_file.relative_to(rpath)),
                        "lineno": node.lineno
                    })
                elif isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
                    symbols.append({
                        "name": node.name,
                        "type": "function",
                        "file": str(py_file.relative_to(rpath)),
                        "lineno": node.lineno
                    })
        except Exception:
            pass

    return symbols

