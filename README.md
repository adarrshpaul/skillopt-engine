# SkillOpt Engine

The SkillOpt Engine is a disciplined, Claude Code Harness-inspired governance framework for multi-agent coding workflows. It provides strict routing, safety guarantees, and evidentiary test pipelines for running local AI models on hardware-constrained systems, specifically targeting Apple Silicon with a strict **16GB RAM limit**.

## The Novel Intention
The core thesis of the SkillOpt Engine is that **we can achieve SWE-bench level multi-agent reasoning on consumer hardware (16GB RAM) without sacrificing context or model capability.** 
Instead of relying on cloud APIs or attempting to load massive models concurrently (which causes catastrophic disk swapping and freezes), SkillOpt uses a highly orchestrated **Maker-Checker ping-pong architecture**. It systematically spins up, queries, and evicts large models (Ling-mini-2.0 and Ornith-9B) sequentially in the same shared memory space, achieving enterprise-grade multi-agent reasoning entirely locally.

---

## Core Architecture

### 1. The Orchestrator (`orchestrator.py`)
- **Multi-Agent Routing**: Uses `Ling-3.0` as the "Planner" and "Reviewer" subagents via native MLX (`mlx_cli.py`), while `Ornith-9B` executes "Coder" tasks via a local Ollama daemon.
- **Severity-Tiered Review Loop**: Implements a strict Maker-Checker loop. The Maker (Coder) has access to 5 local tools (read_file, run_command, etc.) to generate code. The Checker (Reviewer) evaluates it. If the Checker rejects it, the loop continues up to 3 times per subtask.
- **Evidentiary Output**: Automatically generates a `completion_report.md` ledger at the end of execution to provide proof of validation, and dumps structural crashes into a deduped DPO JSONL for later fine-tuning.

### 2. Sandbox Execution Environment (`autoqa/sandbox.py`)
- **Native Venv Isolation**: Instead of using Docker or Orbstack (which introduce a persistent 2-4GB VM tax that violates our 16GB ceiling), SkillOpt uses native Python virtual environments (`venv`) to evaluate generated patches natively.
- **True Execution**: Generated code is applied via `git apply` and evaluated using the target repository's actual test suite (e.g., `pytest`), rather than relying on unreliable LLM grading.

### 3. Admission Controller & Traffic Shaping
- **P1 (Interactive)**: High-priority token bucket for user interactions.
- **P2 (Planner Tasks)**: FIFO queue for complex task execution, with preemption capabilities.
- **P3 (Background)**: Opportunistic scheduling for tasks like FAISS vector indexing, dynamically throttled based on CPU utilization.

---

## Safety & Governance (The Good Things)

1. **Memory Overlap Protection & Eviction Failsafes**: The orchestrator strictly polls the Ollama `/api/ps` endpoint. It enforces a 15-second wait to ensure the Coder model is completely unloaded from Unified Memory before spinning up the Reviewer model, preventing the 16GB ceiling from being breached.
2. **Orphan Cleanup (`killpg`)**: `mlx_cli.py` is invoked using `start_new_session=True`. If the 180-second hard timeout is hit, `os.killpg()` ensures the entire process group is wiped out, preventing zombie grandchildren from leaking VRAM across hundreds of benchmark runs.
3. **DPO Deduplication**: The `reporter.py` engine strips `<HEX>`, `<UUID>`, and `<PATH>` data from raw unstructured crashes, generating deterministic structural hashes. This prevents thousands of identical exception logs from polluting the DPO dataset.

---

## Current Benchmarks & Known Issues

### 📊 SWE-Bench Lite Adapter Benchmarks
- **Instance**: `django__django-11422`
- **Output Quality**: The Coder (`Ornith:9b`) successfully diagnosed the required `argparse` injection in `manage.py`, adding the `--tracking` flag and threading it through kwargs to the target functions.
- **Execution Speed**: Due to the rigorous Maker/Checker looping (up to 3 iterations per subtask) and the sequential model loading to preserve RAM, a single SWE-bench instance takes **~10-15 minutes**.
- **Scale Estimations**: Running the full 300-instance SWE-Bench Lite dataset takes approximately **50-75 hours** sequentially. 

### ⚠️ Known Issues
1. **Model Deadlocks (Exit Code 28)**: Heavy ping-ponging between MLX (GPU) and Ollama on Apple Silicon can occasionally cause the Ollama daemon to freeze and hit the 5-minute HTTP timeout limit. Restarting the daemon clears the GPU hang.
2. **Missing `tests/` directories in Sandbox**: Since we are bypassing Docker containers, some local test commands attempt to run on missing paths unless the full target repository is perfectly mirrored locally. 

---

## ABC-Bench Dual-Container Architecture

For advanced benchmarks like **ABC-Bench** that require heavy backend deployment (which would normally crush a 16GB Mac), we have introduced a **Dual-Container Cloud-Hybrid Architecture**. 

Please see the [Free-Tier Cloud Sandboxes Guide](FREE_TIER_SANDBOXES.md) for full instructions on how to configure `terminal-bench` with remote Docker hosts like GitHub Codespaces, Gitpod, and E2B.

---

## Getting Started

### Prerequisites
- macOS (Apple Silicon optimized, 16GB RAM strict limit)
- Python 3.11+
- `uv` or `pip` for dependency management

### Installation
```bash
# Install dependencies
pip install pytest psutil anyio
```

### Running the QA Harness
```bash
# Run the SWE-Bench adapter
python -m pytest autoqa/tests/ -v -s
```
