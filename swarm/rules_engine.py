"""
Swarm Architecture Rules Engine (Global & Project-Specific Enforcement)
Enforces Clean Architecture across all Swarm sub-agents, loop pipelines, and Lead Advisor synthesis:
1. Small Functions (≤ 30-35 lines, single responsibility)
2. Small Classes & 1 Domain Class per file
3. Dependency Injection (DI) & Inversion of Control (IoC)
4. Loose coupling, high cohesion, and high refactorability
5. Project-specific rule discovery (RULE.md, GEMINI.md, CLAUDE.md, .cursorrules)
"""

import os
from pathlib import Path
from typing import Dict, Any, List, Optional
from swarm.config import GLOBAL_RULES_FILE
from swarm.logger import log_event

GLOBAL_RULES_PATH = GLOBAL_RULES_FILE

DEFAULT_GLOBAL_RULES = """# Global Swarm Architecture & Code Quality Standards

All generated code, sub-agent drafts, and Lead Advisor implementations MUST strictly adhere to these 5 Clean Architecture pillars:

## 1. Small, Single-Responsibility Functions
- Maximum 25–35 lines per function.
- A function does exactly one thing, with zero hidden side-effects.
- Deeply nested control flow (more than 2 levels) is refactored into early-returns (guard clauses) or separate helper functions.

## 2. Small Classes & One Domain Class Per File
- Strict single responsibility principle (SRP). No monolithic "god objects" or "manager" anti-patterns.
- 1 Domain entity / model / value-object per dedicated file (`domain/user.py`, `models/order.ts`, etc.).
- File structure reflects domain boundaries cleanly.

## 3. Dependency Injection (DI) & Inversion of Control (IoC)
- Classes and functions MUST receive dependencies via constructors, arguments, or DI containers.
- Never hardcode concrete service instantiations (`new DatabaseClient()`) inside domain/service business logic.
- Interface-first design: Code against abstractions/protocols to ensure trivial unit test mocking and hot-swappability.

## 4. High Refactorability & Loose Coupling
- Clear layer separation (Domain ➔ Application/Use-Cases ➔ Infrastructure/Adapters).
- Pure business logic has zero dependencies on external frameworks or UI layers.
- Changes in database drivers or UI components must require zero changes to domain models.

## 5. Defensive & Observable Implementation
- Explicit typed contracts (Pydantic / TypeScript types / Type Hints).
- Structured error handling with descriptive exception types rather than generic catch-alls.
- Always include automated unit test coverage alongside code changes.
"""

def init_global_rules():
    """Initializes the global rules file if not present."""
    if not GLOBAL_RULES_PATH.exists():
        GLOBAL_RULES_PATH.parent.mkdir(parents=True, exist_ok=True)
        GLOBAL_RULES_PATH.write_text(DEFAULT_GLOBAL_RULES, encoding="utf-8")

def get_global_rules() -> str:
    """Returns the content of the global rules file."""
    init_global_rules()
    try:
        return GLOBAL_RULES_PATH.read_text(encoding="utf-8")
    except Exception:
        return DEFAULT_GLOBAL_RULES

def save_global_rules(content: str) -> bool:
    """Updates the global rules file."""
    try:
        GLOBAL_RULES_PATH.parent.mkdir(parents=True, exist_ok=True)
        GLOBAL_RULES_PATH.write_text(content, encoding="utf-8")
        log_event("info", "rules", "Updated Swarm Global Architecture Rules")
        return True
    except Exception as e:
        log_event("error", "rules", f"Failed saving global rules: {e}")
        return False

def discover_project_rules(repo_path: str) -> Dict[str, Any]:
    """
    Scans the selected repository directory for project-specific rules:
    Checks RULE.md, GEMINI.md, CLAUDE.md, .cursorrules, .agents/rules, etc.
    """
    if not repo_path:
        return {"has_rules": False, "source": None, "content": ""}

    rp = Path(repo_path)
    if not rp.exists() or not rp.is_dir():
        return {"has_rules": False, "source": None, "content": ""}

    candidate_files = [
        rp / "RULE.md",
        rp / "GEMINI.md",
        rp / "CLAUDE.md",
        rp / ".cursorrules",
        rp / "AGENTS.md",
        rp / ".gemini" / "GEMINI.md",
        rp / ".claude" / "CLAUDE.md"
    ]

    for candidate in candidate_files:
        if candidate.exists() and candidate.is_file():
            try:
                text = candidate.read_text(encoding="utf-8", errors="ignore")
                if text.strip():
                    log_event("info", "rules", f"Loaded project rules from {candidate.name} in {rp.name}")
                    return {
                        "has_rules": True,
                        "source": candidate.name,
                        "file_path": str(candidate),
                        "content": text.strip()
                    }
            except Exception:
                pass

    return {"has_rules": False, "source": None, "content": ""}

def format_enforced_rules_prompt(repo_path: str = "", learned_rules: Optional[List[str]] = None) -> str:
    """
    Constructs an authoritative rules block containing Global Clean Architecture Rules,
    repository-specific project rules, and dynamically evolved lessons learned.
    """
    global_text = get_global_rules().strip()
    proj_info = discover_project_rules(repo_path)

    sections = [
        "=== [GLOBAL ARCHITECTURE RULES (MANDATORY ENFORCEMENT)] ===",
        global_text
    ]

    if proj_info["has_rules"]:
        sections.append(f"\n=== [PROJECT-SPECIFIC RULES ({proj_info['source']})] ===")
        sections.append(proj_info["content"])

    if learned_rules:
        clean_rules = [r.strip() for r in learned_rules if r and r.strip()]
        if clean_rules:
            sections.append("\n=== [DYNAMIC LESSONS LEARNED & EVOLVED INVARIANTS (DO NOT REPEAT MISTAKES)] ===")
            for idx, rule in enumerate(clean_rules, 1):
                sections.append(f"{idx}. {rule}")

    return "\n\n".join(sections)
