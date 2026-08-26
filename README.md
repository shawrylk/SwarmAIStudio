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

### 2b. 🔁 Autonomous Loop Lifecycle (Real Git + GitHub)
The Auto-Loop runs a full, honest lifecycle per goal:
1. Opens an isolated branch `swarm/loop-<id>` and a GitHub tracking issue.
2. Decomposes the goal into PM/Dev/QA/Review tasks and — when the `project` token
   scope is present — **breaks them onto a GitHub Projects board** (one card per task,
   moved to *Done* as each is verified).
3. Writes real files, runs the real test suite, and commits per task.
4. On success: merges the branch into the default branch, **deletes the merged branch**,
   and closes the issue with evidence.
5. **If no code was produced**, it says so plainly — no bogus merge, and the issue is left
   **open** with an explanation (small local models sometimes emit no applicable code).

> The Projects board needs the `project` gh scope once:
> `gh auth refresh -s project`. Without it the loop logs a one-line notice and continues.

### 3. 💬 Multi-Chat Persistence (`~/.swarm/sessions/`)
* Create, rename, delete, and switch between multiple chat sessions on the collapsible left sidebar.
* All conversation history, prompts, status timelines, and generated Markdown Artifacts are persisted across page refreshes and LAN devices.

### 4. 📁 Remote Artifact Vault & LAN Multi-PC Reader
* Centralized artifact storage at `~/.swarm/artifacts/`.
* Read, copy, or download generated reports over LAN via `/api/artifacts/read?path=...`. Reads are confined to the artifact vault (`~/.swarm/artifacts/`); paths outside it are rejected.

### 5. 📚 Capacity Matrix Legend
* Live keyword-filterable catalog in the **Swarm Topology** tab, auto-scanned from every installed agent skill on the host (typically 50+), showing trigger conditions, toolgroups, and capabilities.
* Sub-agents scale dynamically from **1 to 8** GPU continuous-batching slots per task, drawn from the specialist roster (Security, Performance, Architecture, QA, Scout, Database, Draftsman, and more).

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

Everything runs through a single command, **`swarm`**:

```bash
swarm web                 # launch the web console + API (default command)
swarm web --port 9000     # custom port
swarm version             # print version
swarm --help              # see all commands

# From a source checkout without installing:
./bin/swarm web
```

Or use the Makefile shortcuts:

```bash
make run       # foreground server (swarm web)
make start     # background production daemon
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
| `make docker-up` | Build & run the full stack via Docker Compose (detached) |
| `make docker-down` | Stop and remove the Docker Compose stack |
| `make docker-logs` | Tail container logs |
| `swarm web --port 9000` | Start server on a custom port |
| `swarm version` | Print the installed version |

---

## 🐳 Docker Deployment

One command builds and launches the studio in the background:

```bash
make docker-up          # build + run detached (or: docker compose up -d --build)
make docker-logs        # tail logs
make docker-down        # stop & remove
```

Then open **`http://localhost:8080`**.

**Configuration** (env vars, all optional):

| Variable | Default | Purpose |
|---|---|---|
| `SWARM_PORT` | `8080` | Host port to publish |
| `REPOS_DIR` | `~/Documents/GitHub` | Folder of git repos to mount **read-write** so the GitHub Desktop suite and autonomous loop can stage, commit, stash, and create worktrees |
| `LFM_URL` | `host.docker.internal:8034` | Local GPU LFM host — runs on the **host machine**, reached from the container via `host.docker.internal` |

```bash
# Example: publish on 9000 and mount a different projects folder
SWARM_PORT=9000 REPOS_DIR=~/code docker compose up -d --build
```

Notes:
* Vault, sessions, and rules persist in the named `swarm-data` volume across restarts.
* Repos are mounted **read-write** (earlier revisions mounted them `:ro`, which silently broke commit/stage/stash). The image ships a default git identity and marks mounts as safe directories so loop commits succeed.
* The Claude/Gemini/Context7 CLIs are host tools and are not bundled in the image; when absent the orchestrator honestly reports `fallback_local` and routes through the local GPU model.
* A `HEALTHCHECK` polls `/api/repos`; `docker ps` shows `healthy` once ready.

---

## 🧪 Running Unit Tests

```bash
make test
```
```
test_file_search_scales_to_1_scout (tests.test_dynamic_planner.TestDynamicSwarmPlanner) ... ok
test_bug_fix_scales_to_4_surgical_agents (tests.test_dynamic_planner.TestDynamicSwarmPlanner) ... ok
test_deep_audit_scales_to_6_specialists (tests.test_dynamic_planner.TestDynamicSwarmPlanner) ... ok
test_artifact_read_rejects_path_traversal (tests.test_security.TestServerSecurity) ... ok
test_openapi_scanner_ignores_tsconfig (tests.test_contracts_engine.TestContractsEngine) ... ok
test_qwen_oracle_reports_unavailable_honestly (tests.test_orchestrator_safety.TestOracleSafety) ... ok
... (full suite)

----------------------------------------------------------------------
Ran 107 tests

OK
```

---

## 📄 License
This project is open-source under the [MIT License](LICENSE).
