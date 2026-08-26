"""
Dynamic Agent Skill Scanner & Capacity Catalog Engine
Discovers all installed skills across ~/.agents/skills/, Antigravity builtins, and Swarm capabilities.
Parses SKILL.md metadata, descriptions, tools, and dynamically assigns them to sub-agent roles.
"""

import os
import re
from pathlib import Path
from typing import List, Dict, Any, Optional

try:
    import yaml
except ImportError:
    yaml = None

from swarm.logger import log_event

SKILL_DIRECTORIES = [
    Path.home() / ".agents" / "skills",
    Path.home() / ".gemini" / "antigravity-cli" / "builtin" / "skills",
    Path.home() / ".claude" / "skills"
]

SPECIAL_NAMES = {
    "github": "GitHub",
    "gitnexus": "GitNexus",
    "tdd": "TDD",
    "mcp": "MCP",
    "cbo": "CBO",
    "api": "API",
    "gsd": "GSD",
    "agy": "AGY",
    "ui": "UI",
    "ux": "UX",
    "cli": "CLI",
    "pdg": "PDG",
    "wcag": "WCAG",
    "pr": "PR",
    "qa": "QA",
    "ci": "CI",
    "cd": "CD",
    "rfc": "RFC",
    "adr": "ADR",
    "html": "HTML",
    "css": "CSS",
    "ast": "AST",
    "btw": "BTW Quick Query",
    "lint": "Lint & Code Quality",
    "userinterface-wiki": "User Interface Wiki",
    "spike-wrap-up": "Spike Wrap-Up",
    "context7-docs": "Context7 Live Documentation & API Scout",
    "planner-cbo": "Cost-Based Optimizer (CBO) Query Planner",
}

KNOWN_SKILL_CATEGORIES = {
    # 1. Security & Audit
    "security-review": "Security & Audit",
    "best-practices": "Security & Audit",
    "gitnexus-taint-analysis": "Security & Audit",
    "forensics": "Security & Audit",
    "code-optimizer": "Security & Audit",
    "lint": "Security & Audit",
    "review": "Security & Audit",
    "permissioned-github": "Security & Audit",
    "permissioned_github": "Security & Audit",
    "web-quality-audit": "Security & Audit",
    "web_quality_audit": "Security & Audit",

    # 2. Testing & QA
    "test": "Testing & QA",
    "tdd": "Testing & QA",
    "debug-like-expert": "Testing & QA",
    "verify-before-complete": "Testing & QA",
    "gitnexus-debugging": "Testing & QA",

    # 3. Architecture & Planning
    "design-an-interface": "Architecture & Planning",
    "api-design": "Architecture & Planning",
    "decompose-into-slices": "Architecture & Planning",
    "grill-me": "Architecture & Planning",
    "write-milestone-brief": "Architecture & Planning",
    "create-workflow": "Architecture & Planning",
    "migrate-workflows": "Architecture & Planning",
    "migrate_workflows": "Architecture & Planning",
    "planner-cbo": "Architecture & Planning",
    "planner_cbo": "Architecture & Planning",

    # 4. Frontend & UI/UX
    "frontend-design": "Frontend & UI/UX",
    "make-interfaces-feel-better": "Frontend & UI/UX",
    "react-best-practices": "Frontend & UI/UX",
    "userinterface-wiki": "Frontend & UI/UX",
    "web-design-guidelines": "Frontend & UI/UX",
    "core-web-vitals": "Frontend & UI/UX",
    "accessibility": "Frontend & UI/UX",
    "generative_ui": "Frontend & UI/UX",
    "generative-ui": "Frontend & UI/UX",

    # 5. Codebase Intelligence & Git
    "gitnexus-cli": "Codebase Intelligence & Git",
    "gitnexus-exploring": "Codebase Intelligence & Git",
    "gitnexus-impact-analysis": "Codebase Intelligence & Git",
    "gitnexus-pdg-query": "Codebase Intelligence & Git",
    "gitnexus-pr-review": "Codebase Intelligence & Git",
    "gitnexus-refactoring": "Codebase Intelligence & Git",
    "github-workflows": "Codebase Intelligence & Git",
    "dependency-upgrade": "Codebase Intelligence & Git",
    "gitnexus-guide": "Codebase Intelligence & Git",

    # 6. Agent Extensions & Customization
    "create-skill": "Agent Extensions & Customization",
    "create-mcp-server": "Agent Extensions & Customization",
    "create-gsd-extension": "Agent Extensions & Customization",
    "find-skills": "Agent Extensions & Customization",
    "agy-customizations": "Agent Extensions & Customization",
    "agy_customizations": "Agent Extensions & Customization",
    "antigravity_guide": "Agent Extensions & Customization",
    "antigravity-guide": "Agent Extensions & Customization",

    # 7. Research & Documentation
    "write-docs": "Research & Documentation",
    "spike-wrap-up": "Research & Documentation",
    "spike_wrap_up": "Research & Documentation",
    "btw": "Research & Documentation",
    "handoff": "Research & Documentation",
    "observability": "Research & Documentation",
    "agent-browser": "Research & Documentation",
    "ask-claude": "Research & Documentation",
    "context7-docs": "Research & Documentation",
    "context7_docs": "Research & Documentation",
}

CATEGORY_METADATA = {
    "Security & Audit": {
        "role": "🛡️ Security Threat Auditor",
        "icon": "🛡️",
        "tools": ["threat_audit", "taint_analysis", "vuln_scan", "secret_hunt", "lint_engine"]
    },
    "Testing & QA": {
        "role": "🧪 QA & Regression Verifier",
        "icon": "🧪",
        "tools": ["pytest", "tdd_loop", "diagnostics", "contract_verify", "regression_trace"]
    },
    "Architecture & Planning": {
        "role": "📐 Architecture & Solution Planner",
        "icon": "📐",
        "tools": ["system_design", "interface_spec", "dag_scheduler", "cbo_explain", "slice_decomposer"]
    },
    "Frontend & UI/UX": {
        "role": "🎨 UI/UX & Design Engineer",
        "icon": "🎨",
        "tools": ["ui_inspect", "css_audit", "a11y_check", "web_vitals", "component_render"]
    },
    "Codebase Intelligence & Git": {
        "role": "🌿 Codebase Intelligence & Git Specialist",
        "icon": "🌿",
        "tools": ["gitnexus_graph", "call_graph", "impact_analysis", "diff_inspect", "refactor_engine"]
    },
    "Agent Extensions & Customization": {
        "role": "🧩 Agent Extension & Customization Specialist",
        "icon": "🧩",
        "tools": ["mcp_inspector", "skill_forge", "plugin_builder", "customization_loader"]
    },
    "Research & Documentation": {
        "role": "📚 Research & Technical Documenter",
        "icon": "📚",
        "tools": ["doc_extract", "ctx7", "browser_cli", "external_consult", "observability_probe"]
    }
}

SKILL_SPECIFIC_TOOLS = {
    "gitnexus-taint-analysis": ["taint_analysis", "cfg_dataflow", "ast_grep", "source_sink_trace"],
    "security-review": ["threat_model", "stride_audit", "auth_scan", "secret_hunt"],
    "code-optimizer": ["perf_profiler", "ast_search", "memory_leak_detect", "latency_audit"],
    "lint": ["eslint_engine", "biome_fix", "prettier", "lsp_diagnostics"],
    "best-practices": ["best_practices_audit", "security_check", "compatibility_lint"],
    "forensics": ["gsd_postmortem", "activity_trace", "journal_log", "crash_diagnose"],
    "permissioned-github": ["gh_auth_audit", "permission_guard", "token_scope"],
    "permissioned_github": ["gh_auth_audit", "permission_guard", "token_scope"],
    "review": ["diff_review", "stride_audit", "code_quality", "security_check"],
    "tdd": ["tdd_loop", "red_green_refactor", "pytest", "unit_test"],
    "test": ["pytest", "test_runner", "coverage", "contract_verify"],
    "debug-like-expert": ["hypothesis_test", "root_cause_analysis", "lsp_diagnostics", "trace_logger"],
    "verify-before-complete": ["evidence_verifier", "assertion_check", "compile_check", "contract_verify"],
    "gitnexus-debugging": ["gitnexus_graph", "call_stack_trace", "error_origin", "pdg_query"],
    "design-an-interface": ["design_twice", "api_sketch", "contract_spec", "interface_matrix"],
    "api-design": ["rest_schema", "graphql_spec", "idempotency_check", "versioning"],
    "decompose-into-slices": ["vertical_slice", "tracer_bullet", "dependency_graph", "roadmap_gen"],
    "grill-me": ["decision_interrogator", "tradeoff_matrix", "stress_test", "risk_eval"],
    "write-milestone-brief": ["prd_synthesis", "milestone_spec", "scope_boundary", "context_doc"],
    "create-workflow": ["workflow_yaml", "dag_builder", "step_validator"],
    "migrate-workflows": ["workflow_migration", "yaml_transformer", "legacy_bridge"],
    "migrate_workflows": ["workflow_migration", "yaml_transformer", "legacy_bridge"],
    "planner-cbo": ["cbo_explain", "dag_scheduler", "cardinality_estimator", "cost_matrix"],
    "planner_cbo": ["cbo_explain", "dag_scheduler", "cardinality_estimator", "cost_matrix"],
    "frontend-design": ["component_design", "css_system", "theme_tokens", "ui_polish"],
    "make-interfaces-feel-better": ["micro_interactions", "animation_springs", "optical_alignment", "shadow_engine"],
    "react-best-practices": ["vercel_react_lint", "bundle_size", "server_components", "memo_audit"],
    "userinterface-wiki": ["ux_heuristics", "typography_audit", "audio_ux", "touch_target"],
    "web-design-guidelines": ["guideline_eval", "color_contrast", "viewport_compat"],
    "core-web-vitals": ["lcp_optimizer", "cls_preventer", "inp_profiler", "lighthouse"],
    "accessibility": ["wcag_audit", "aria_tree", "keyboard_nav", "screen_reader"],
    "generative_ui": ["html_widget_builder", "dynamic_iframe", "canvas_render"],
    "generative-ui": ["html_widget_builder", "dynamic_iframe", "canvas_render"],
    "web-quality-audit": ["lighthouse_audit", "page_experience", "seo_check", "perf_metric"],
    "web_quality_audit": ["lighthouse_audit", "page_experience", "seo_check", "perf_metric"],
    "gitnexus-cli": ["gitnexus_index", "graph_query", "wiki_generate", "cli_runner"],
    "gitnexus-exploring": ["symbol_graph", "execution_flow", "module_map", "caller_callee"],
    "gitnexus-impact-analysis": ["impact_radius", "blast_surface", "dependency_cascade", "safe_check"],
    "gitnexus-pdg-query": ["pdg_query", "cdg_edge", "reaching_def", "guard_tracer"],
    "gitnexus-pr-review": ["pr_diff_audit", "risk_matrix", "coverage_gap", "pr_impact"],
    "gitnexus-refactoring": ["symbol_rename", "safe_extract", "module_split", "refactor_graph"],
    "github-workflows": ["actions_lint", "ci_matrix", "workflow_trace", "secret_validation"],
    "dependency-upgrade": ["dep_triage", "npm_audit", "pip_upgrade", "breaking_changes"],
    "gitnexus-guide": ["gitnexus_docs", "mcp_help", "graph_schema", "query_examples"],
    "create-skill": ["skill_forge", "skill_spec", "skill_validator", "prompt_engineer"],
    "create-mcp-server": ["mcp_scaffold", "jsonrpc_spec", "mcp_inspector", "eval_builder"],
    "create-gsd-extension": ["gsd_api", "tui_component", "event_hook", "command_reg"],
    "find-skills": ["skill_registry", "capability_scout", "install_helper"],
    "agy-customizations": ["agy_loader", "skill_priority", "rule_binder", "mcp_config"],
    "agy_customizations": ["agy_loader", "skill_priority", "rule_binder", "mcp_config"],
    "antigravity_guide": ["agy_sitemap", "quick_ref", "ide_guide", "cli_manual"],
    "antigravity-guide": ["agy_sitemap", "quick_ref", "ide_guide", "cli_manual"],
    "write-docs": ["doc_authoring", "markdown_formatter", "rfc_spec", "adr_writer"],
    "spike-wrap-up": ["spike_synthesizer", "skill_packager", "findings_extractor"],
    "spike_wrap_up": ["spike_synthesizer", "skill_packager", "findings_extractor"],
    "btw": ["quick_context", "side_channel", "memory_lookup"],
    "handoff": ["session_checkpoint", "continue_doc", "state_snapshot"],
    "observability": ["structured_log", "health_check", "failure_telemetry", "metric_probe"],
    "agent-browser": ["playwright_cli", "dom_inspector", "action_replay", "page_scrape"],
    "ask-claude": ["claude_escalation", "deep_reasoner", "model_bridge"],
    "context7-docs": ["ctx7", "context7-mcp", "library_resolve", "api_scout"],
    "context7_docs": ["ctx7", "context7-mcp", "library_resolve", "api_scout"],
}

def format_skill_name(skill_id: str, raw_name: str) -> str:
    """Formats a skill ID or raw name into a clean, human-readable title."""
    if skill_id in SPECIAL_NAMES:
        return SPECIAL_NAMES[skill_id]
    if raw_name in SPECIAL_NAMES:
        return SPECIAL_NAMES[raw_name]
    if raw_name and raw_name != skill_id and (" " in raw_name or any(c.isupper() for c in raw_name)):
        return raw_name
    words = skill_id.replace("_", "-").split("-")
    formatted = [SPECIAL_NAMES.get(w.lower(), w.capitalize()) for w in words]
    return " ".join(formatted)

def classify_skill_category(skill_id: str, name: str, description: str) -> str:
    """
    Robust skill categorization with priority matching:
    1. Exact / normalized skill ID dictionary lookup
    2. Word-boundary semantic regex heuristics across name and description
    3. Safe default fallback
    """
    sid_norm = skill_id.lower().replace("_", "-").strip()
    if sid_norm in KNOWN_SKILL_CATEGORIES:
        return KNOWN_SKILL_CATEGORIES[sid_norm]
    if skill_id in KNOWN_SKILL_CATEGORIES:
        return KNOWN_SKILL_CATEGORIES[skill_id]

    text = f"{skill_id} {name} {description}".lower()

    # Priority 1: Testing & QA (check for explicit test/debug/verify terms)
    if re.search(r'\b(tdd|test|tests|testing|pytest|unittest|debugger|debugging|debug|repro|verifier|verification|diagnostics|compiler|regression)\b', text):
        return "Testing & QA"

    # Priority 2: Security & Audit
    if re.search(r'\b(security|threat|vulnerability|vulnerabilities|cve|owasp|taint|exploit|secret|sanitize|audit|auditing|lint|linter|linting|forensic|forensics|code-smell|anti-pattern|best-practices|quality-audit|stride)\b', text):
        return "Security & Audit"

    # Priority 3: Frontend & UI/UX
    if re.search(r'\b(frontend|ui|ux|css|html|react|component|components|styling|animation|accessibility|a11y|wcag|vitals|layout|widget|interface-feel|typography)\b', text):
        return "Frontend & UI/UX"

    # Priority 4: Agent Extensions & Customization
    if re.search(r'\b(mcp|mcp-server|customization|customizations|gsd-extension|extension|extensions|plugin|plugins|sidecar|skill-creation|find-skill|skills|antigravity)\b', text):
        return "Agent Extensions & Customization"

    # Priority 5: Architecture & Planning
    if re.search(r'\b(architecture|planner|planning|decompose|slices|milestone|prd|rfc|adr|api-design|design-an-interface|workflow|workflows|cbo|dag)\b', text):
        return "Architecture & Planning"

    # Priority 6: Codebase Intelligence & Git
    if re.search(r'\b(git|github|gitnexus|repository|repo|commit|branch|worktree|stash|diff|refactor|refactoring|pdg|ast|call-graph|dependency-upgrade)\b', text):
        return "Codebase Intelligence & Git"

    # Priority 7: Research & Documentation
    if re.search(r'\b(doc|docs|documentation|context7|browser|scrape|claude|oracle|observability|log|logs|metrics|handoff|spike|research)\b', text):
        return "Research & Documentation"

    return "Research & Documentation"

def parse_skill_markdown(skill_path: Path) -> Optional[Dict[str, Any]]:
    """Parses SKILL.md metadata, extracting YAML frontmatter, title, description, category, and tools."""
    skill_file = skill_path / "SKILL.md"
    if not skill_file.exists():
        if skill_path.is_file() and skill_path.suffix == ".md":
            skill_file = skill_path
        else:
            return None

    try:
        content = skill_file.read_text(encoding="utf-8", errors="ignore")
        skill_id = skill_path.stem if skill_path.is_file() and skill_path.name != "SKILL.md" else (
            skill_path.parent.name if skill_path.name == "SKILL.md" else skill_path.name
        )
        name = skill_id
        description = "Specialized agent capability."

        # Parse YAML frontmatter if present
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                fm_raw = parts[1].strip()
                if yaml:
                    try:
                        meta = yaml.safe_load(fm_raw)
                        if isinstance(meta, dict):
                            if "name" in meta and meta["name"]:
                                name = str(meta["name"]).strip()
                            if "description" in meta and meta["description"]:
                                description = str(meta["description"]).strip()
                    except Exception:
                        pass
                
                # Fallback line-by-line parsing if YAML parser did not set description
                if description == "Specialized agent capability.":
                    lines = fm_raw.splitlines()
                    desc_collecting = False
                    desc_lines = []
                    for line in lines:
                        if line.startswith("name:") and not desc_collecting:
                            name = line.split("name:", 1)[1].strip().strip('"').strip("'")
                        elif line.startswith("description:"):
                            val = line.split("description:", 1)[1].strip()
                            if val in [">", ">-", "|", "|-", ""]:
                                desc_collecting = True
                            else:
                                description = val.strip('"').strip("'")
                        elif desc_collecting:
                            if line.startswith(" ") or line.startswith("\t"):
                                desc_lines.append(line.strip())
                            else:
                                desc_collecting = False
                    if desc_lines:
                        description = " ".join(desc_lines)

        # Format display name
        display_name = format_skill_name(skill_id, name)
        
        # Categorize
        category = classify_skill_category(skill_id, display_name, description)
        
        # Determine tools & role
        cat_meta = CATEGORY_METADATA.get(category, CATEGORY_METADATA["Research & Documentation"])
        sid_norm = skill_id.lower().replace("_", "-").strip()
        tools = SKILL_SPECIFIC_TOOLS.get(skill_id, SKILL_SPECIFIC_TOOLS.get(sid_norm, cat_meta["tools"]))
        role = cat_meta["role"]

        return {
            "id": skill_id,
            "name": display_name,
            "description": description,
            "category": category,
            "role": role,
            "tools": tools,
            "path": str(skill_path)
        }
    except Exception:
        return None

def scan_all_installed_skills() -> List[Dict[str, Any]]:
    """Scans and deduplicates all installed agent skills across defined search paths."""
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
            "category": "Research & Documentation",
            "role": "📚 Research & Technical Documenter",
            "tools": ["ctx7", "context7-mcp", "library_resolve", "api_scout"],
            "path": "builtin/context7"
        }

    if "planner-cbo" not in skills_map:
        skills_map["planner-cbo"] = {
            "id": "planner-cbo",
            "name": "Cost-Based Optimizer (CBO) Query Planner",
            "description": "SQL-style AST analysis, plan enumeration, critical path cost estimation, and DAG execution.",
            "category": "Architecture & Planning",
            "role": "📐 Architecture & Solution Planner",
            "tools": ["cbo_explain", "dag_scheduler", "cardinality_estimator", "cost_matrix"],
            "path": "builtin/planner"
        }

    skill_list = list(skills_map.values())
    skill_list.sort(key=lambda s: (s["category"], s["name"]))
    
    log_event("info", "skills", f"Scanned {len(skill_list)} installed agent skills across {len(SKILL_DIRECTORIES)} sources")
    return skill_list

def read_skill_instructions(skill_info: Dict[str, Any]) -> str:
    """Reads the full instructions / markdown body for a skill."""
    skill_path_str = skill_info.get("path", "")
    if skill_path_str and skill_path_str not in ["builtin/context7", "builtin/planner"]:
        p = Path(skill_path_str)
        skill_file = p / "SKILL.md" if p.is_dir() else p
        if skill_file.exists() and skill_file.is_file():
            try:
                raw_text = skill_file.read_text(encoding="utf-8", errors="ignore").strip()
                # Strip YAML frontmatter
                if raw_text.startswith("---"):
                    parts = raw_text.split("---", 2)
                    if len(parts) >= 3:
                        raw_text = parts[2].strip()
                if raw_text:
                    return raw_text
            except Exception:
                pass

    # Builtin fallback instructions
    sid = skill_info.get("id", "")
    cat = skill_info.get("category", "")
    if sid == "context7-docs":
        return """1. Use ctx7 or Context7 documentation tools to look up latest 2026 library syntax and API contracts.
2. Ground all proposed code and interfaces in version-accurate packages.
3. Reject deprecated patterns and verify method signatures before implementation."""
    elif sid == "planner-cbo":
        return """1. Enumerate candidate execution DAGs and compute critical-path latency and cost.
2. Select minimum-cost execution path with maximum parallelism.
3. Validate dependency ordering and prevent cyclical stalls."""
    elif cat == "Testing & QA" or "test" in sid or "qa" in sid:
        return """1. Never trust prior claims without independent execution evidence.
2. Verify syntax validity, contract invariants, and test assertions.
3. Provide concrete file:line failure reports and actionable repro cases."""
    elif cat == "Security & Audit" or "security" in sid:
        return """1. Audit input boundaries for injection (SQL, Command, XSS, Path Traversal).
2. Verify authentication, authorization, and secret handling.
3. Inspect blast radius and external dependencies for supply-chain risks."""
    elif cat == "Architecture & Planning":
        return """1. Design deep interfaces with minimal surface area and strong information hiding.
2. Decompose complex goals into verifiable vertical slices.
3. Stress-test trade-offs and establish explicit error boundaries."""
    elif cat == "Frontend & UI/UX":
        return """1. Implement polished, responsive, and accessible UI components following WCAG standards.
2. Optimize Core Web Vitals (LCP, INP, CLS) and render performance.
3. Maintain cohesive design tokens, typography, and micro-interactions."""
    elif cat == "Codebase Intelligence & Git":
        return """1. Query dependency graphs and call hierarchies before modifying code.
2. Perform blast radius and impact analysis for all proposed symbol changes.
3. Ensure atomic, safe refactorings and clean version control workflows."""
    
    return f"Execute role directives adhering to {skill_info.get('name', 'Specialist')} best practices and Clean Architecture."

def resolve_and_inject_skill(role: str, task_description: str = "", repo_path: str = "") -> Dict[str, Any]:
    """
    Finds the most relevant SKILL.md file for the given role and task description,
    loads its instructions, and formats an authoritative skill injection prompt.
    """
    all_skills = scan_all_installed_skills()
    skills_by_id = {s["id"]: s for s in all_skills}

    role_clean = (role or "dev").lower().strip()
    task_clean = (task_description or "").lower()

    # Preference ranking per role
    role_preferences = {
        "dev": ["tdd", "best-practices", "code-optimizer", "react-best-practices", "frontend-design", "api-design", "gitnexus-refactoring"],
        "qa": ["verify-before-complete", "test", "tdd", "debug-like-expert", "lint", "web-quality-audit"],
        "review": ["security-review", "review", "best-practices", "observability", "gitnexus-taint-analysis", "gitnexus-pr-review"],
        "security": ["security-review", "review", "best-practices", "gitnexus-taint-analysis", "permissioned-github"],
        "pm": ["write-milestone-brief", "decompose-into-slices", "grill-me", "api-design", "design-an-interface", "create-workflow"],
        "research": ["context7-docs", "gitnexus-exploring", "agent-browser", "ask-claude", "api-design", "write-docs"],
        "arch": ["design-an-interface", "api-design", "decompose-into-slices", "planner-cbo", "context7-docs"],
        "oracle": ["verify-before-complete", "ask-claude", "review", "grill-me", "debug-like-expert"],
        "consensus": ["verify-before-complete", "ask-claude", "review", "grill-me"],
        "judge": ["verify-before-complete", "review", "forensics", "debug-like-expert"]
    }

    prefs = role_preferences.get(role_clean, ["best-practices", "tdd", "verify-before-complete"])

    # Score each candidate skill
    scored_candidates = []
    for skill in all_skills:
        score = 0
        sid = skill["id"]
        s_name = skill["name"].lower()
        s_desc = skill["description"].lower()
        s_cat = skill.get("category", "").lower()

        # Role candidate position score
        if sid in prefs:
            score += max(1, 15 - (prefs.index(sid) * 2))

        # Keyword boosts from task description
        task_words = [w for w in re.split(r'[^a-zA-Z0-9_-]', task_clean) if len(w) >= 3]
        for w in task_words:
            if w in sid or w in s_name:
                score += 8
            elif w in s_desc:
                score += 3
            elif w in s_cat:
                score += 2

        # Specific intent keyword boosts
        if any(k in task_clean for k in ["security", "auth", "owasp", "threat", "injection", "secret", "taint", "vulnerability", "audit"]) and ("security" in sid or "audit" in s_cat or "review" in sid or "taint" in sid):
            score += 25
        if any(k in task_clean for k in ["test", "verify", "assert", "regression", "qa", "diagnostics"]) and ("test" in sid or "verify" in sid or "debug" in sid or "qa" in s_cat):
            score += 25
        if any(k in task_clean for k in ["tdd", "red-green"]) and sid == "tdd":
            score += 30
        if any(k in task_clean for k in ["react", "frontend", "ui", "component", "css", "styling"]) and ("react" in sid or "frontend" in sid or "interface" in sid or "frontend" in s_cat):
            score += 20
        if any(k in task_clean for k in ["doc", "docs", "documentation", "context7", "library", "api"]) and ("doc" in sid or "context7" in sid or "api" in sid or "docs" in s_cat or "research" in s_cat):
            score += 20
        if any(k in task_clean for k in ["perf", "optimize", "slow", "latency", "bottleneck", "cache", "memory"]) and ("optimizer" in sid or "vitals" in sid):
            score += 22
        if any(k in task_clean for k in ["git", "branch", "pr", "commit", "worktree", "merge", "refactor"]) and ("git" in sid or "refactor" in sid or "intelligence" in s_cat):
            score += 20
        if any(k in task_clean for k in ["mcp", "extension", "plugin", "skill"]) and ("mcp" in sid or "skill" in sid or "extension" in sid or "customization" in s_cat):
            score += 20

        scored_candidates.append((score, skill))

    scored_candidates.sort(key=lambda x: x[0], reverse=True)

    # Pick top match
    selected_skill = scored_candidates[0][1] if scored_candidates and scored_candidates[0][0] > 0 else (
        skills_by_id.get(prefs[0]) if prefs and prefs[0] in skills_by_id else all_skills[0]
    )

    instructions = read_skill_instructions(selected_skill)

    tools_str = ", ".join(selected_skill.get("tools", ["read_file", "search"]))
    injection_prompt = f"""=== [DYNAMIC SKILL INJECTION: {selected_skill['name']} ({selected_skill['id']})] ===
Role: {role.upper()}
Skill Category: {selected_skill.get('category', 'Specialist')}
Available Skill Tools: {tools_str}

Skill Directives & Execution Protocol:
{instructions[:2500]}
=================================================================="""

    log_event("info", "skills", f"Injected skill '{selected_skill['id']}' ({selected_skill['name']}) for role '{role}'")

    return {
        "skill_id": selected_skill["id"],
        "skill_name": selected_skill["name"],
        "category": selected_skill.get("category", "Research & Documentation"),
        "role": selected_skill.get("role", f"{role.upper()} Specialist"),
        "tools": selected_skill.get("tools", []),
        "path": selected_skill.get("path", ""),
        "instructions": instructions,
        "injection_prompt": injection_prompt
    }


