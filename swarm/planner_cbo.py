"""
Cost-Based Optimizer (CBO) & Execution DAG Planner

NOTE: This module provides diagnostic/visualization functionality only.
It is NOT in the critical execution path — the advisor chat and auto-dev loop
operate independently of CBO plan selection. The /api/planner/explain endpoint
exposes this as a read-only diagnostic tool.
"""

import time
import json
import asyncio
from typing import List, Dict, Any, Optional, Tuple
from swarm.logger import log_event
from swarm.context7_engine import fetch_latest_doc_context
from swarm.memory_engine import read_disk_memory_files, format_disk_memory_prompt_block
from swarm.web_scout import search_web_live, format_web_scout_prompt_block

class SwarmPlanNode:
    def __init__(
        self,
        node_id: str,
        name: str,
        operator: str, # DISK_MEMORY_SCAN, WEB_SCOUT, FACT_CHECK_AUDIT, INDEX_SCAN, DOC_FETCH, CODE_DRAFT, SYNTAX_VERIFY, THREAT_AUDIT, CONSENSUS_MERGE, SYNTHESIZE
        role: str,
        assigned_agent: str,
        slot_name: str,
        dependencies: List[str] = None,
        estimated_cost_ms: float = 400.0,
        estimated_tokens: int = 1000,
        prompt_instruction: str = ""
    ):
        self.node_id = node_id
        self.name = name
        self.operator = operator
        self.role = role
        self.assigned_agent = assigned_agent
        self.slot_name = slot_name
        self.dependencies = dependencies or []
        self.estimated_cost_ms = estimated_cost_ms
        self.estimated_tokens = estimated_tokens
        self.prompt_instruction = prompt_instruction
        self.status = "pending" # pending, running, completed, failed
        self.output = ""
        self.actual_duration_ms = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.node_id,
            "name": self.name,
            "operator": self.operator,
            "role": self.role,
            "assigned_agent": self.assigned_agent,
            "slot": self.slot_name,
            "dependencies": self.dependencies,
            "estimated_cost_ms": self.estimated_cost_ms,
            "estimated_tokens": self.estimated_tokens,
            "status": self.status,
            "output": self.output,
            "actual_duration_ms": self.actual_duration_ms
        }

class SwarmExecutionPlan:
    def __init__(
        self,
        plan_id: str,
        strategy_name: str,
        nodes: List[SwarmPlanNode],
        confidence_score: float,
        strategy_rationale: str
    ):
        self.plan_id = plan_id
        self.strategy_name = strategy_name
        self.nodes = nodes
        self.confidence_score = confidence_score
        self.strategy_rationale = strategy_rationale
        
        # Calculate Plan Metrics
        self.total_estimated_tokens = sum(n.estimated_tokens for n in nodes)
        self.parallelism_width = self._calculate_max_parallelism()
        self.critical_path_cost_ms = self._calculate_critical_path()
        self.cost_score = self._compute_cost_score()

    def _calculate_max_parallelism(self) -> int:
        levels: Dict[int, int] = {}
        for n in self.nodes:
            depth = len(n.dependencies)
            levels[depth] = levels.get(depth, 0) + 1
        return max(levels.values()) if levels else 1

    def _calculate_critical_path(self) -> float:
        node_map = {n.node_id: n for n in self.nodes}
        costs = {}
        
        for n in self.nodes:
            if not n.dependencies:
                costs[n.node_id] = n.estimated_cost_ms
            else:
                max_dep_cost = max((costs.get(dep, 0) for dep in n.dependencies), default=0)
                costs[n.node_id] = max_dep_cost + n.estimated_cost_ms
                
        return max(costs.values()) if costs else 0.0

    def _compute_cost_score(self) -> float:
        time_penalty = (self.critical_path_cost_ms / 1000.0) * 0.35
        token_penalty = (self.total_estimated_tokens / 1000.0) * 0.15
        risk_penalty = (1.0 - self.confidence_score) * 8.0
        return round(time_penalty + token_penalty + risk_penalty, 2)

    def generate_explain_plan(self) -> str:
        """SQL-like EXPLAIN output."""
        lines = [
            f"=== EXPLAIN SWARM QUERY PLAN: {self.strategy_name} (Plan ID: {self.plan_id}) ===",
            f"Cost Score: {self.cost_score} · Confidence: {int(self.confidence_score*100)}% · Parallel Width: {self.parallelism_width}x",
            f"Estimated Critical Path: {round(self.critical_path_cost_ms, 1)}ms · Est. Tokens: {self.total_estimated_tokens}",
            f"Optimization Rationale: {self.strategy_rationale}",
            "",
            "EXECUTION DAG:"
        ]
        for i, n in enumerate(self.nodes):
            deps_str = f" [Depends on: {', '.join(n.dependencies)}]" if n.dependencies else " [Root]"
            lines.append(f"  {i+1}. -> {n.operator} on {n.slot_name}: '{n.name}' ({n.assigned_agent}){deps_str} (est. {n.estimated_cost_ms}ms)")
        lines.append("="*60)
        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "strategy_name": self.strategy_name,
            "cost_score": self.cost_score,
            "confidence_score": self.confidence_score,
            "critical_path_cost_ms": self.critical_path_cost_ms,
            "total_estimated_tokens": self.total_estimated_tokens,
            "parallelism_width": self.parallelism_width,
            "strategy_rationale": self.strategy_rationale,
            "explain_text": self.generate_explain_plan(),
            "nodes": [n.to_dict() for n in self.nodes]
        }

def analyze_intent_statistics(message: str, repo_ctx: Dict[str, Any]) -> Dict[str, Any]:
    msg_lower = message.lower()
    
    has_code_keywords = any(k in msg_lower for k in ["fix", "implement", "build", "refactor", "patch", "error", "exception", "test", "null"])
    has_audit_keywords = any(k in msg_lower for k in ["review", "audit", "security", "performance", "check diff", "quality", "scan"])
    has_doc_keywords = any(k in msg_lower for k in ["doc", "documentation", "context7", "latest api", "library", "sdk", "how to use", "guide", "what is", "explain"])
    has_architecture_keywords = any(k in msg_lower for k in ["design", "architecture", "tradeoff", "distributed", "caching", "blueprint"])
    is_simple_lookup = any(k in msg_lower for k in ["find file", "where is", "locate", "grep"])

    repo_files_count = len(repo_ctx.get("files_sample", [])) if repo_ctx else 0
    has_uncommitted_diff = bool(repo_ctx.get("diff")) if repo_ctx else False

    complexity = 4
    if has_audit_keywords: complexity += 3
    if has_code_keywords: complexity += 2
    if has_uncommitted_diff: complexity += 1
    if has_architecture_keywords: complexity += 2
    if is_simple_lookup: complexity = 1
    complexity = min(10, complexity)

    return {
        "complexity_score": complexity,
        "is_simple_lookup": is_simple_lookup,
        "has_code_keywords": has_code_keywords,
        "has_audit_keywords": has_audit_keywords,
        "has_doc_keywords": has_doc_keywords,
        "has_architecture_keywords": has_architecture_keywords,
        "has_uncommitted_diff": has_uncommitted_diff,
        "repo_name": repo_ctx.get("name", "") if repo_ctx else "",
        "token_cardinality": len(message.split()) * 8
    }

def enumerate_candidate_plans(stats: Dict[str, Any], user_msg: str) -> List[SwarmExecutionPlan]:
    candidates = []

    # ─────────────────────────────────────────────────────────────
    # Candidate Plan 1: Parallel Multi-Agent Cross-Check & Disk Grounding DAG (Fast Latency)
    # ─────────────────────────────────────────────────────────────
    p1_nodes = [
        SwarmPlanNode("n1", "Disk Memory & Config Scan", "DISK_MEMORY_SCAN", "memory", "🔍 Disk Memory & Rules Scout", "Disk I/O", estimated_cost_ms=150, estimated_tokens=500),
        SwarmPlanNode("n2", "Live Web & Documentation Scout", "WEB_SCOUT", "web", "🌐 Web & Context7 Scout", "Web Fetch", estimated_cost_ms=250, estimated_tokens=600),
        SwarmPlanNode("n3", "Adversarial Red-Team Cross-Check", "FACT_CHECK_AUDIT", "adversary", "🛡️ Adversarial Fact-Checker", "GPU Slot 1", dependencies=["n1", "n2"], estimated_cost_ms=450, estimated_tokens=1000),
        SwarmPlanNode("n4", "Domain Specialist Solution Draft", "CODE_DRAFT", "dev", "⚙️ Surgical Solution Draftsman", "GPU Slot 2", dependencies=["n1", "n2"], estimated_cost_ms=500, estimated_tokens=1200),
        SwarmPlanNode("n5", "Cross-Check Consensus & Synthesis", "SYNTHESIZE", "architect", "👑 Lead Advisor Arbiter", "Local GPU Arbiter", dependencies=["n3", "n4"], estimated_cost_ms=650, estimated_tokens=1500)
    ]
    p1 = SwarmExecutionPlan("plan_fast_latency", "Parallel Multi-Agent Cross-Check & Disk Grounding DAG", p1_nodes, confidence_score=0.98, strategy_rationale="Spawns concurrent disk memory, web scout, adversarial fact-checking, and solution drafting slots.")
    candidates.append(p1)

    # ─────────────────────────────────────────────────────────────
    # Candidate Plan 2: Multi-Vector Security, QA & Regression Verification DAG
    # ─────────────────────────────────────────────────────────────
    p2_nodes = [
        SwarmPlanNode("n1", "Disk Memory & AST Symbol Scan", "DISK_MEMORY_SCAN", "memory", "🔍 Disk Memory & AST Scout", "GPU Slot 1", estimated_cost_ms=250, estimated_tokens=600),
        SwarmPlanNode("n2", "Live Context7 Doc Verification", "DOC_FETCH", "web", "🌐 Web & Context7 Scout", "Web Fetch", estimated_cost_ms=300, estimated_tokens=700),
        SwarmPlanNode("n3", "Surgical Code Draft", "CODE_DRAFT", "dev", "⚙️ Surgical Code Draftsman", "GPU Slot 2", dependencies=["n1", "n2"], estimated_cost_ms=600, estimated_tokens=1300),
        SwarmPlanNode("n4", "LSP & Syntax Contract Verification", "SYNTAX_VERIFY", "qa", "🧪 LSP & Syntax Verifier", "GPU Slot 3", dependencies=["n3"], estimated_cost_ms=400, estimated_tokens=800),
        SwarmPlanNode("n5", "Zero-Drift Threat & Security Audit", "THREAT_AUDIT", "security", "🛡️ Threat & Security Auditor", "GPU Slot 4", dependencies=["n3"], estimated_cost_ms=450, estimated_tokens=900),
        SwarmPlanNode("n6", "Lead Advisor Consensus & Sign-off", "SYNTHESIZE", "architect", "👑 Lead Advisor Arbiter", "Local GPU Arbiter", dependencies=["n4", "n5"], estimated_cost_ms=700, estimated_tokens=1600)
    ]
    p2 = SwarmExecutionPlan("plan_multi_verified", "Multi-Vector Security & QA Verification DAG", p2_nodes, confidence_score=0.99, strategy_rationale="Full multi-vector verification across QA, Security, and Code Draftsman slots.")
    candidates.append(p2)

    # ─────────────────────────────────────────────────────────────
    # Candidate Plan 3: Live Web & Context7 Grounded Cross-Check DAG
    # ─────────────────────────────────────────────────────────────
    p3_nodes = [
        SwarmPlanNode("n1", "Context7 Live Documentation Lookup", "DOC_FETCH", "docs", "📚 Context7 Documentation Scout", "Context7 MCP", estimated_cost_ms=300, estimated_tokens=800),
        SwarmPlanNode("n2", "Disk Memory & Config Facts", "DISK_MEMORY_SCAN", "memory", "🔍 Disk Memory Scout", "Disk I/O", estimated_cost_ms=150, estimated_tokens=500),
        SwarmPlanNode("n3", "Version-Accurate Code Synthesis", "CODE_DRAFT", "dev", "⚙️ Surgical Code Draftsman", "GPU Slot 1", dependencies=["n1", "n2"], estimated_cost_ms=550, estimated_tokens=1400),
        SwarmPlanNode("n4", "Adversarial Hallucination Cross-Check", "FACT_CHECK_AUDIT", "adversary", "🛡️ Adversarial Fact-Checker", "GPU Slot 2", dependencies=["n1", "n3"], estimated_cost_ms=450, estimated_tokens=1000),
        SwarmPlanNode("n5", "Lead Advisor Authoritative Synthesis", "SYNTHESIZE", "architect", "👑 Lead Advisor Arbiter", "Local GPU Arbiter", dependencies=["n3", "n4"], estimated_cost_ms=650, estimated_tokens=1600)
    ]
    p3 = SwarmExecutionPlan("plan_c7_consensus", "Context7-Grounded Adversarial Cross-Check DAG", p3_nodes, confidence_score=0.98, strategy_rationale="Grounds implementation with live web / Context7 docs and cross-checks with adversarial red-team.")
    candidates.append(p3)

    return candidates

def optimize_and_select_best_plan(message: str, repo_ctx: Dict[str, Any]) -> Tuple[SwarmExecutionPlan, List[SwarmExecutionPlan], Dict[str, Any]]:
    """
    Cost-Based Optimizer (CBO) selection algorithm:
    Evaluates statistics, enumerates candidate plans, and returns (optimal_plan, candidates, stats).
    """
    stats = analyze_intent_statistics(message, repo_ctx)
    candidates = enumerate_candidate_plans(stats, message)

    if stats["is_simple_lookup"]:
        best_plan = candidates[0] # Plan 1 (Fast Latency)
    elif stats["has_doc_keywords"] or "context7" in message.lower() or "latest api" in message.lower():
        best_plan = candidates[2] # Plan 3 (Context7 Consensus)
    elif stats["has_code_keywords"] or stats["has_audit_keywords"] or stats["has_uncommitted_diff"]:
        best_plan = candidates[1] # Multi-Vector Security & QA DAG
    else:
        best_plan = candidates[0] # Parallel Multi-Agent Cross-Check DAG

    log_event("info", "planner", f"Optimizer selected plan: '{best_plan.strategy_name}' (Cost: {best_plan.cost_score}, Conf: {int(best_plan.confidence_score*100)}%)")
    return best_plan, candidates, stats

async def execute_plan_dag(
    plan: SwarmExecutionPlan,
    repo_block: str,
    user_prompt: str,
    repo_path: str = "",
    status_callback = None
) -> Dict[str, Any]:
    """
    Executes the optimal plan DAG according to topological dependency constraints.
    Nodes with all dependencies resolved run concurrently on Liquid LFM continuous slots.
    """
    from swarm.orchestrator import query_local_slot, query_gemini, update_agent_status
    
    t0 = time.time()
    node_map = {n.node_id: n for n in plan.nodes}
    completed_nodes: set = set()
    node_outputs: Dict[str, str] = {}

    log_event("info", "planner", f"Starting execution of DAG '{plan.strategy_name}' ({len(plan.nodes)} nodes)")

    while len(completed_nodes) < len(plan.nodes):
        ready_nodes = [
            n for n in plan.nodes
            if n.node_id not in completed_nodes
            and n.status == "pending"
            and all(dep in completed_nodes for dep in n.dependencies)
        ]

        if not ready_nodes:
            break

        async def run_single_node(node: SwarmPlanNode):
            node.status = "running"
            node_t0 = time.time()
            if status_callback:
                status_callback(f"⚡ [DAG Step] Executing {node.operator}: '{node.name}' ({node.assigned_agent})...")

            dep_context = "\n".join([f"[{node_map[dep].name} Output]:\n{node_outputs.get(dep, '')}" for dep in node.dependencies])

            try:
                if node.operator == "DISK_MEMORY_SCAN":
                    mem_data = read_disk_memory_files(repo_path)
                    node.output = format_disk_memory_prompt_block(mem_data)

                elif node.operator == "WEB_SCOUT":
                    web_res = search_web_live(user_prompt)
                    node.output = format_web_scout_prompt_block(user_prompt, web_res)

                elif node.operator == "FACT_CHECK_AUDIT":
                    prompt = f"""Task: Adversarial Red-Team & Fact-Checker.
User Question / Task:
{user_prompt}

Grounded Files & Predecessor Context:
{dep_context}

Instructions:
1. Scrutinize the user question, assumptions, and potential solutions for any falsehoods or hallucinations.
2. Cross-check claims directly against the verified disk memory and web evidence provided above.
3. Identify edge cases, missing prerequisites, or misconceptions.
4. Issue a clear VERDICT (VERIFIED / CHALLENGED / REFINED) with concise evidence."""
                    node.output = await query_local_slot(prompt, system="You are the Adversarial Fact-Checker and Red-Team Auditor.")

                elif node.operator in ["INDEX_SCAN", "CODE_DRAFT", "SYNTAX_VERIFY", "THREAT_AUDIT"]:
                    prompt = f"{repo_block}\n\nUser Request: {user_prompt}\n\nPredecessor Findings & Grounded Facts:\n{dep_context}\n\nInstruction: Execute {node.name} rigorously with Clean Architecture rules (≤35 lines per function, single responsibility, DI)."
                    node.output = await query_local_slot(prompt, system=f"You are the {node.assigned_agent}. Specialized in {node.role.upper()}.")

                elif node.operator == "SYNTHESIZE":
                    synthesis_prompt = f"""You are the Lead Advisor & Chief AI Architect.
User Request:
{user_prompt}

Multi-Agent DAG Execution Findings Across Specialized Slots:
{dep_context}

Instructions:
1. Synthesize these findings into an authoritative, complete, production-ready response.
2. Present a Multi-Agent Cross-Check & Verification Summary table at the top:
   | Specialist Sub-Agent | Role | Cross-Check Verdict | Key Verified Fact |
3. Enforce Clean Architecture (≤35 lines per function, single responsibility, DI, high refactorability).
"""
                    node.output = await query_gemini(synthesis_prompt)

                node.status = "completed"
            except Exception as e:
                node.status = "failed"
                node.output = f"Execution error: {e}"

            node.actual_duration_ms = round((time.time() - node_t0) * 1000, 1)
            node_outputs[node.node_id] = node.output
            completed_nodes.add(node.node_id)
            return node

        await asyncio.gather(*(run_single_node(n) for n in ready_nodes))

    total_duration = round(time.time() - t0, 2)
    final_output = node_outputs.get(plan.nodes[-1].node_id, "Plan execution completed.")
    
    return {
        "plan_id": plan.plan_id,
        "strategy_name": plan.strategy_name,
        "cost_score": plan.cost_score,
        "duration_sec": total_duration,
        "nodes": [n.to_dict() for n in plan.nodes],
        "final_output": final_output
    }

