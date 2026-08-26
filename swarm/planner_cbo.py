"""
Cost-Based Optimizer (CBO) & Swarm DAG Execution Planner for Swarm AI Studio
Inspired by SQL Query Optimizers (PostgreSQL, Spark Catalyst) and advanced agent harnesses.

Features:
1. Intent & Statistical Analysis (Cardinality, Risk Factors, Manifest dependencies).
2. Plan Enumeration: Generates alternative execution DAGs (Fast Scout, Deep Verified, Consensus-Grounded).
3. Cost-Based Scoring: Balances Estimated Latency (ms), Token Budget, Confidence %, and GPU Slot Availability.
4. Topological DAG Executor: Executes non-dependent sub-agent nodes in parallel across GPU continuous batching slots.
5. SQL-Style 'EXPLAIN PLAN' generator for full transparency.
"""

import time
import json
import asyncio
from typing import List, Dict, Any, Optional, Tuple
from swarm.logger import log_event
from swarm.context7_engine import fetch_latest_doc_context

class SwarmPlanNode:
    def __init__(
        self,
        node_id: str,
        name: str,
        operator: str, # INDEX_SCAN, DOC_FETCH, CODE_DRAFT, SYNTAX_VERIFY, THREAT_AUDIT, CONSENSUS_MERGE, SYNTHESIZE
        role: str,
        assigned_agent: str,
        slot_name: str,
        dependencies: List[str] = None,
        estimated_cost_ms: float = 500.0,
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
        # Sum costs along the dependency chain
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
        # Lower score = better cost efficiency
        # Cost = (CriticalPath / 1000) * 0.4 + (Tokens / 1000) * 0.2 + (1.0 - Confidence) * 10
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
    
    # Statistical Indicators
    has_code_keywords = any(k in msg_lower for k in ["fix", "implement", "build", "refactor", "patch", "error", "exception", "test", "null"])
    has_audit_keywords = any(k in msg_lower for k in ["review", "audit", "security", "performance", "check diff", "quality", "scan"])
    has_doc_keywords = any(k in msg_lower for k in ["doc", "documentation", "context7", "latest api", "library", "sdk", "how to use", "guide"])
    has_architecture_keywords = any(k in msg_lower for k in ["design", "architecture", "tradeoff", "distributed", "caching", "blueprint"])
    is_simple_lookup = any(k in msg_lower for k in ["find file", "where is", "locate", "grep"])

    repo_files_count = len(repo_ctx.get("files_sample", [])) if repo_ctx else 0
    has_uncommitted_diff = bool(repo_ctx.get("diff")) if repo_ctx else False

    # Cardinality estimation (1 to 10 scale)
    complexity = 3
    if has_audit_keywords: complexity += 3
    if has_code_keywords: complexity += 2
    if has_uncommitted_diff: complexity += 2
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
    # Candidate Plan 1: Fast Parallel Scan (Optimized for Latency)
    # ─────────────────────────────────────────────────────────────
    p1_nodes = [
        SwarmPlanNode("n1", "Structural Index Scan", "INDEX_SCAN", "scout", "🔍 Symbol & AST Scout", "GPU Slot 1", estimated_cost_ms=300, estimated_tokens=600),
        SwarmPlanNode("n2", "Direct Code Patch", "CODE_DRAFT", "dev", "⚙️ Surgical Code Draftsman", "GPU Slot 2", dependencies=["n1"], estimated_cost_ms=750, estimated_tokens=1200),
        SwarmPlanNode("n3", "Lead Advisor Verdict", "SYNTHESIZE", "architect", "👑 Gemini Lead Advisor", "Gemini Pro", dependencies=["n2"], estimated_cost_ms=1100, estimated_tokens=1500)
    ]
    p1 = SwarmExecutionPlan("plan_fast_latency", "Fast-Path Streamlined Pipeline", p1_nodes, confidence_score=0.82, strategy_rationale="Minimizes latency with direct 2-stage execution.")
    candidates.append(p1)

    # ─────────────────────────────────────────────────────────────
    # Candidate Plan 2: Cost-Optimized Multi-Stage Verified DAG (Standard)
    # ─────────────────────────────────────────────────────────────
    p2_nodes = [
        SwarmPlanNode("n1", "AST Symbol & Dependency Scan", "INDEX_SCAN", "scout", "🔍 Symbol & AST Scout", "GPU Slot 1", estimated_cost_ms=350, estimated_tokens=700),
        SwarmPlanNode("n2", "Surgical Code Draft", "CODE_DRAFT", "dev", "⚙️ Surgical Code Draftsman", "GPU Slot 2", dependencies=["n1"], estimated_cost_ms=900, estimated_tokens=1400),
        SwarmPlanNode("n3", "LSP & Syntax Contract Verification", "SYNTAX_VERIFY", "qa", "🧪 LSP & Syntax Verifier", "GPU Slot 3", dependencies=["n2"], estimated_cost_ms=600, estimated_tokens=900),
        SwarmPlanNode("n4", "Zero-Drift Blast Radius Audit", "THREAT_AUDIT", "security", "🛡️ Blast Radius Gatekeeper", "GPU Slot 4", dependencies=["n2"], estimated_cost_ms=650, estimated_tokens=1000),
        SwarmPlanNode("n5", "Lead Advisor Synthesis & Sign-off", "SYNTHESIZE", "architect", "👑 Gemini Lead Advisor", "Gemini Pro", dependencies=["n3", "n4"], estimated_cost_ms=1300, estimated_tokens=1800)
    ]
    p2 = SwarmExecutionPlan("plan_multi_verified", "Cost-Optimized Multi-Stage Verified DAG", p2_nodes, confidence_score=0.95, strategy_rationale="Parallel QA and Security verification branches merge into Lead Advisor.")
    candidates.append(p2)

    # ─────────────────────────────────────────────────────────────
    # Candidate Plan 3: Live Context7 Doc-Grounded & Adversarial Consensus DAG
    # ─────────────────────────────────────────────────────────────
    p3_nodes = [
        SwarmPlanNode("n1", "Context7 Live Documentation Lookup", "DOC_FETCH", "docs", "📚 Context7 Documentation Scout", "Context7 MCP", estimated_cost_ms=450, estimated_tokens=800),
        SwarmPlanNode("n2", "Codebase Symbol Indexing", "INDEX_SCAN", "scout", "🔍 Symbol & AST Scout", "GPU Slot 1", estimated_cost_ms=350, estimated_tokens=700),
        SwarmPlanNode("n3", "Version-Accurate Code Synthesis", "CODE_DRAFT", "dev", "⚙️ Surgical Code Draftsman", "GPU Slot 2", dependencies=["n1", "n2"], estimated_cost_ms=950, estimated_tokens=1500),
        SwarmPlanNode("n4", "Qwen 3.8 Adversarial Consensus Peer", "CONSENSUS_MERGE", "oracle", "🔮 Qwen Web Oracle", "Qwen Web", dependencies=["n3"], estimated_cost_ms=1100, estimated_tokens=1200),
        SwarmPlanNode("n5", "Security Threat & Blast Radius Audit", "THREAT_AUDIT", "security", "🛡️ Security Threat Auditor", "GPU Slot 3", dependencies=["n3"], estimated_cost_ms=650, estimated_tokens=900),
        SwarmPlanNode("n6", "Lead Advisor Authoritative Synthesis", "SYNTHESIZE", "architect", "👑 Gemini Lead Advisor", "Gemini Pro", dependencies=["n4", "n5"], estimated_cost_ms=1400, estimated_tokens=2000)
    ]
    p3 = SwarmExecutionPlan("plan_c7_consensus", "Context7-Grounded Adversarial Consensus DAG", p3_nodes, confidence_score=0.98, strategy_rationale="Grounds implementation with live 2026 Context7 docs and cross-checks with Qwen Oracle.")
    candidates.append(p3)

    # ─────────────────────────────────────────────────────────────
    # Candidate Plan 4: Claude Code CLI Escalation & Deep Reasoning DAG
    # ─────────────────────────────────────────────────────────────
    p4_nodes = [
        SwarmPlanNode("n1", "AST Symbol & Dependency Scan", "INDEX_SCAN", "scout", "🔍 Symbol & AST Scout", "GPU Slot 1", estimated_cost_ms=350, estimated_tokens=700),
        SwarmPlanNode("n2", "Claude Code Deep Reasoning Synthesis", "CODE_DRAFT", "claude", "🧠 Claude Code CLI (v2.1)", "Claude 3.7", dependencies=["n1"], estimated_cost_ms=1800, estimated_tokens=2500),
        SwarmPlanNode("n3", "LSP & Syntax Contract Verification", "SYNTAX_VERIFY", "qa", "🧪 LSP & Syntax Verifier", "GPU Slot 2", dependencies=["n2"], estimated_cost_ms=600, estimated_tokens=900),
        SwarmPlanNode("n4", "Qwen 3.8 Invariant Consensus Gate", "CONSENSUS_MERGE", "oracle", "🔮 Qwen Web Oracle", "Qwen Web", dependencies=["n2"], estimated_cost_ms=1100, estimated_tokens=1200),
        SwarmPlanNode("n5", "Lead Advisor Sign-off & Architecture Lock", "SYNTHESIZE", "architect", "👑 Gemini Lead Advisor", "Gemini Pro", dependencies=["n3", "n4"], estimated_cost_ms=1400, estimated_tokens=2000)
    ]
    p4 = SwarmExecutionPlan("plan_claude_escalation", "Claude Code CLI Escalation & Deep Reasoning DAG", p4_nodes, confidence_score=0.99, strategy_rationale="Dispatches high-complexity reasoning directly through Claude Code CLI (v2.1).")
    candidates.append(p4)

    return candidates

def optimize_and_select_best_plan(message: str, repo_ctx: Dict[str, Any]) -> Tuple[SwarmExecutionPlan, List[SwarmExecutionPlan], Dict[str, Any]]:
    """
    Cost-Based Optimizer (CBO) selection algorithm:
    Evaluates statistics, enumerates candidate plans, and returns (optimal_plan, candidates, stats).
    """
    stats = analyze_intent_statistics(message, repo_ctx)
    candidates = enumerate_candidate_plans(stats, message)

    # Decision Matrix
    if stats["is_simple_lookup"]:
        best_plan = candidates[0] # Plan 1 (Fast Latency)
    elif stats["has_doc_keywords"] or "how" in message.lower() or "latest" in message.lower():
        best_plan = candidates[2] # Plan 3 (Context7 Grounded)
    elif stats["complexity_score"] >= 6 or stats["has_architecture_keywords"]:
        best_plan = candidates[2] if stats["has_doc_keywords"] else candidates[1]
    else:
        # Pick lowest Cost Score
        best_plan = min(candidates, key=lambda p: p.cost_score)

    log_event("info", "planner", f"Optimizer selected plan: '{best_plan.strategy_name}' (Cost: {best_plan.cost_score}, Conf: {int(best_plan.confidence_score*100)}%)")
    return best_plan, candidates, stats

async def execute_plan_dag(
    plan: SwarmExecutionPlan,
    repo_block: str,
    user_prompt: str,
    status_callback = None
) -> Dict[str, Any]:
    """
    Executes the optimal plan DAG according to topological dependency constraints.
    Nodes with all dependencies resolved run concurrently on Liquid LFM continuous slots.
    """
    from swarm.orchestrator import query_local_slot, query_gemini, query_qwen_web, update_agent_status
    
    t0 = time.time()
    node_map = {n.node_id: n for n in plan.nodes}
    completed_nodes: set = set()
    node_outputs: Dict[str, str] = {}

    log_event("info", "planner", f"Starting execution of DAG '{plan.strategy_name}' ({len(plan.nodes)} nodes)")

    while len(completed_nodes) < len(plan.nodes):
        # Find all ready nodes
        ready_nodes = [
            n for n in plan.nodes
            if n.node_id not in completed_nodes
            and n.status == "pending"
            and all(dep in completed_nodes for dep in n.dependencies)
        ]

        if not ready_nodes:
            # Check for deadlock
            break

        # Launch ready nodes in parallel
        async def run_single_node(node: SwarmPlanNode):
            node.status = "running"
            node_t0 = time.time()
            if status_callback:
                status_callback(f"⚡ [DAG Step] Executing {node.operator}: '{node.name}' ({node.assigned_agent})...")

            # Collect outputs of predecessor nodes
            dep_context = "\n".join([f"[{node_map[dep].name} Output]:\n{node_outputs.get(dep, '')}" for dep in node.dependencies])

            try:
                if node.operator == "DOC_FETCH":
                    # Extract query keyword
                    words = [w for w in user_prompt.split() if len(w) > 2]
                    target_lib = words[0] if words else "fastapi"
                    node.output = fetch_latest_doc_context(target_lib, user_prompt)

                elif node.operator in ["INDEX_SCAN", "CODE_DRAFT", "SYNTAX_VERIFY", "THREAT_AUDIT"]:
                    prompt = f"{repo_block}\n\nUser Request: {user_prompt}\n\nPredecessor Findings:\n{dep_context}\n\nInstruction: Execute {node.name} rigorously."
                    node.output = await query_local_slot(prompt, system=f"You are the {node.assigned_agent}. Specialized in {node.role.upper()}.")

                elif node.operator == "CONSENSUS_MERGE":
                    qwen_prompt = f"Request: {user_prompt}\n\nDraft Implementation:\n{dep_context}\n\nProvide adversarial cross-check, edge cases, and verification."
                    node.output = await query_qwen_web(qwen_prompt)

                elif node.operator == "SYNTHESIZE":
                    synthesis_prompt = f"""You are the Lead Advisor.
User Request:
{user_prompt}

DAG Execution Findings Across All Nodes:
{dep_context}

Synthesize these findings into an authoritative, complete, production-ready verdict and implementation.
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
    # Find final synthesis output
    final_output = node_outputs.get(plan.nodes[-1].node_id, "Plan execution completed.")
    
    return {
        "plan_id": plan.plan_id,
        "strategy_name": plan.strategy_name,
        "cost_score": plan.cost_score,
        "duration_sec": total_duration,
        "nodes": [n.to_dict() for n in plan.nodes],
        "final_output": final_output
    }
