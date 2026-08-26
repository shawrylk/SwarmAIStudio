# 🌌 Swarm AI Studio

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![GPU Acceleration](https://img.shields.io/badge/GPU-RTX%20Continuous%20Batching-green.svg)]()
[![Git Ready](https://img.shields.io/badge/Git-GitHub%20Desktop%20Suite-orange.svg)]()

**Swarm AI Studio** is a high-performance, GPU-accelerated multi-agent AI coding environment and 100% mouse-driven GitHub Desktop web suite. It orchestrates local continuous batching LLMs (Liquid LFM 2.5 on GPU) with cloud consensus oracles (Gemini Pro / Qwen 3.8 Max) to deliver task-aware code reviews, surgical implementations, and real-time Git management.

---

## 🏛️ System Architecture

```mermaid
graph TD
    User["Developer Web Console / LAN Client"] -->|HTTP / JSON API| Server["Swarm AI Studio Server (:8080)"]
    
    subgraph Level 1: Chief Orchestrator
        Server -->|Decompose & Synthesize| Gemini["👑 Gemini Lead Advisor (gemini-3.1-pro-high)"]
    end

    subgraph Level 2: Adversarial Consensus & GPU Host
        Server -->|Local GPU Batching| LFM["⚡ Local GPU Swarm Host (:8034)"]
        Server -->|Frontier 2.4T MoE| Qwen["🔮 Qwen 3.8 Max Oracle (chat.qwen.ai)"]
    end

    subgraph Level 3: Dynamic Specialist Sub-Agents (1 to 8 GPU Slots)
        LFM --> Sec["🛡️ Security Threat Auditor (OWASP)"]
        LFM --> Perf["⚡ Performance Profiler (Latency & Mem)"]
        LFM --> Arch["📐 Architecture & Modular Gate"]
        LFM --> QA["🧪 QA & LSP Compiler Verifier"]
        LFM --> Scout["🔍 Symbol & AST Scout (GitNexus)"]
        LFM --> DB["💾 Database & I/O Inspector"]
        LFM --> Code["⚙️ Surgical Code Draftsman"]
        LFM --> Gate["🛡️ Blast Radius Gatekeeper"]
    end

    subgraph Git Workspace Engine
        Server --> GHD["🌿 Full GitHub Desktop Web Suite"]
        GHD --> Diffs["Unified High-Contrast Colored Diffs"]
        GHD --> Branches["Interactive Branch Switcher & Creator"]
        GHD --> Sync["Ahead/Behind Fetch, Pull & Push"]
        GHD --> Stash["Stashes & Worktrees Manager"]
    end
```

---

## ✨ Core Features

### 1. 🎯 Task-Aware Dynamic Swarm Planning (1 to 8 GPU Slots)
* **Zero Blind Steps:** Automatically evaluates task complexity and dynamically scales sub-agent count:
  * **File Searches / Symbol Lookups:** 1 Scout sub-agent (`find_by_name`, `grep_search`).
  * **Surgical Bug Fixes & Patches:** 4 sub-agents (`Symbol Scout`, `Surgical Draftsman`, `LSP Verifier`, `Blast Radius Gate`).
  * **Deep Multi-Vector Code Audits:** 6 to 8 specialized sub-agents running concurrently across GPU continuous batching slots.
* **Dynamic Skill Allocation:** Injects domain-tailored system prompts and skills (`OWASP Injection Hunter`, `Latency Optimizer`, `Roslyn Contract Gate`, `Database Inspector`).

### 2. 🌿 Complete GitHub Desktop Web Suite (100% Mouse-Driven)
* **Visual Git Client:** Inspect uncommitted changes, select files via checkboxes, and stage/unstage with 1 click.
* **Unified Colored Diff Viewer:** Deep blue chunk headers (`@@ -L,S +L,S @@`), soft emerald additions (`+`), and rose deletions (`-`).
* **Interactive Branch Menu (`🌿 master ▾`):** Search, switch branches, or create new branches with one click.
* **Sync & Remotes:** Ahead/Behind badges with direct **Fetch**, **Pull**, and **Push** buttons.
* **Worktrees & Stashes:** Create isolated worktrees and save/pop stashes from interactive dialogs.
* **History Inspector:** Chronological commit cards with author, date, and full commit diff viewer.

### 3. 💬 Multi-Chat Persistence (`~/.swarm/sessions/`)
* Create, rename, delete, and switch between multiple chat sessions on the collapsible left sidebar.
* All conversation history, prompts, status timelines, and generated Markdown Artifacts are persisted across page refreshes and LAN devices.

### 4. 📁 Remote Artifact Vault & LAN Multi-PC Reader
* Centralized artifact storage at `~/.swarm/artifacts/`.
* Read, copy, or download generated reports over LAN via `/api/artifacts/read?path=...`.

### 5. 📚 Capacity Matrix Legend (12 Specialized Roles)
* Live keyword filterable catalog in the **Swarm Topology** tab showing trigger conditions, toolgroups, and capabilities for all 12 specialized sub-agent roles.

---

## ⚡ Quickstart & Installation

### Prerequisites
* Python 3.10+
* Git
* *(Optional)* NVIDIA GPU with CUDA for local Liquid LFM 2.5 continuous batching on port `8034`.

### 1. Clone and Setup
```bash
git clone https://github.com/shawrylk/SwarmAIStudio.git
cd SwarmAIStudio

# Run automated setup
make install
```

### 2. Launch Swarm AI Studio
```bash
# Launch interactive foreground server
make run

# Or launch background production daemon
make start
```

Open **`http://localhost:8080`** (or access from any LAN PC at **`http://<YOUR_IP>:8080`**).

---

## 🛠️ CLI & Makefile Reference

| Command | Description |
|---|---|
| `make run` | Launch server on port 8080 in foreground |
| `make dev` | Run server in interactive development mode |
| `make start` | Launch background daemon and write to `swarm_studio.log` |
| `make stop` | Gracefully terminate running background instance |
| `make test` | Run automated unit test suite (`tests/`) |
| `make clean` | Remove `__pycache__`, build artifacts, and caches |
| `bin/swarm-studio --port 9000` | Start server on custom port |

---

## 🐳 Docker Deployment

You can run Swarm AI Studio in Docker:

```bash
docker compose up -d
```

---

## 🧪 Running Unit Tests

```bash
make test
```
```
test_file_search_scales_to_1_scout (tests.test_dynamic_planner.TestDynamicSwarmPlanner) ... ok
test_bug_fix_scales_to_4_surgical_agents (tests.test_dynamic_planner.TestDynamicSwarmPlanner) ... ok
test_deep_audit_scales_to_6_specialists (tests.test_dynamic_planner.TestDynamicSwarmPlanner) ... ok
test_find_git_repos_discovers_repositories (tests.test_git_engine.TestGitEngine) ... ok
test_get_full_github_desktop_state (tests.test_git_engine.TestGitEngine) ... ok
test_session_lifecycle (tests.test_sessions.TestSessions) ... ok

----------------------------------------------------------------------
Ran 6 tests in 0.042s

OK
```

---

## 📄 License
This project is open-source under the [MIT License](LICENSE).
