"""
Dynamic Agent Skill Scanner & Capacity Catalog Engine
Discovers all 45+ installed skills across ~/.agents/skills/, Antigravity builtins, and Swarm capabilities.
Parses SKILL.md metadata, descriptions, tools, and dynamically assigns them to sub-agent roles.
"""

import os
import re
from pathlib import Path
from typing import List, Dict, Any, Optional
from swarm.logger import log_event

SKILL_DIRECTORIES = [
    Path.home() / ".agents" / "skills",
    Path.home() / ".gemini" / "antigravity-cli" / "builtin" / "skills",
    Path.home() / ".claude" / "skills"
]

def parse_skill_markdown(skill_path: Path) -> Optional[Dict[str, Any]]:
    skill_file = skill_path / "SKILL.md"
    if not skill_file.exists():
        if skill_path.is_file() and skill_path.suffix == ".md":
            skill_file = skill_path
        else:
            return None

    try:
        content = skill_file.read_text(encoding="utf-8", errors="ignore")
        
        name = skill_path.name.replace("-", " ").title()
        description = "Specialized agent capability."
        category = "General"
        tools = ["read_file", "search"]
        
        # Parse YAML frontmatter if present
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                frontmatter = parts[1]
                for line in frontmatter.splitlines():
                    if line.startswith("name:"):
                        name = line.split("name:", 1)[1].strip().strip('"').strip("'")
                    elif line.startswith("description:"):
                        description = line.split("description:", 1)[1].strip().strip('"').strip("'")

        # Infer category and tools based on name/description
        k = (name + " " + description + " " + skill_path.name).lower()
        if any(w in k for w in ["git", "branch", "pr", "commit", "worktree", "stash", "workflow", "ci"]):
            category = "Git & CI/CD"
            tools = ["git_engine", "diff", "branch", "worktree"]
        elif any(w in k for w in ["security", "auth", "owasp", "threat", "vulnerability", "leak"]):
            category = "Security & Audit"
            tools = ["auth_scan", "injection_audit", "secret_hunt"]
        elif any(w in k for w in ["ui", "frontend", "react", "css", "interface", "design", "accessibility", "a11y"]):
            category = "Frontend & UX"
            tools = ["css_audit", "react_profile", "a11y_check"]
        elif any(w in k for w in ["test", "tdd", "qa", "verify", "regression", "compiler", "debug", "forensics"]):
            category = "Testing & QA"
            tools = ["pytest", "lsp_diagnostics", "contract_verify"]
        elif any(w in k for w in ["doc", "context7", "write", "brief", "milestone", "api-design", "rfc"]):
            category = "Docs & Knowledge"
            tools = ["ctx7", "context7_docs", "write_docs"]
        elif any(w in k for w in ["perf", "optimize", "cache", "memory", "database", "sql", "latency"]):
            category = "Performance & Architecture"
            tools = ["latency_profile", "sql_audit", "cache_design"]
        else:
            category = "Core & Reasoning"
            tools = ["reasoning", "solution_blueprint"]

        role_map = {
            "Git & CI/CD": "🌿 Version Control Specialist",
            "Security & Audit": "🛡️ Security Threat Auditor",
            "Frontend & UX": "🎨 UI/UX & Design Engineer",
            "Testing & QA": "🧪 QA & Regression Verifier",
            "Docs & Knowledge": "📚 Context7 & Technical Documenter",
            "Performance & Architecture": "⚡ Latency & Database Optimizer",
            "Core & Reasoning": "💡 Technical Solution Architect"
        }

        return {
            "id": skill_path.name,
            "name": name,
            "description": description,
            "category": category,
            "role": role_map.get(category, "Specialist Sub-Agent"),
            "tools": tools,
            "path": str(skill_path)
        }
    except Exception:
        return None

def scan_all_installed_skills() -> List[Dict[str, Any]]:
    """Scans and deduplicates all installed agent skills."""
    skills_map: Dict[str, Dict[str, Any]] = {}

    for base_dir in SKILL_DIRECTORIES:
        if base_dir.exists() and base_dir.is_dir():
            for item in base_dir.iterdir():
                if item.name.startswith("."):
                    continue
                skill_info = parse_skill_markdown(item)
                if skill_info and skill_info["id"] not in skills_map:
                    skills_map[skill_info["id"]] = skill_info

    if "context7-docs" not in skills_map:
        skills_map["context7-docs"] = {
            "id": "context7-docs",
            "name": "Context7 Live Documentation & API Scout",
            "description": "Real-time version-accurate documentation extraction via Context7 MCP & CLI for modern frameworks.",
            "category": "Docs & Knowledge",
            "role": "📚 Context7 Documentation & API Scout",
            "tools": ["ctx7", "context7-mcp", "library_resolve"],
            "path": "builtin/context7"
        }

    if "planner-cbo" not in skills_map:
        skills_map["planner-cbo"] = {
            "id": "planner-cbo",
            "name": "Cost-Based Optimizer (CBO) Query Planner",
            "description": "SQL-style AST analysis, plan enumeration, critical path cost estimation, and DAG execution.",
            "category": "Performance & Architecture",
            "role": "⚡ Swarm Query Optimizer",
            "tools": ["cbo_explain", "dag_scheduler", "cardinality_estimator"],
            "path": "builtin/planner"
        }

    skill_list = list(skills_map.values())
    skill_list.sort(key=lambda s: (s["category"], s["name"]))
    
    log_event("info", "skills", f"Scanned {len(skill_list)} installed agent skills across {len(SKILL_DIRECTORIES)} sources")
    return skill_list
