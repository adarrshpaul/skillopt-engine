# 🚀 SkillOpt Engine: Self-Improving Local AI Coding Stack

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Backend: MLX GPU](https://img.shields.io/badge/Hardware-Apple_Silicon_MLX-blue.svg)](https://github.com/ml-explore/mlx)
[![Architecture: Dual--Layer](https://img.shields.io/badge/Architecture-CAA_Steering_%2B_GBNF-green.svg)](#dual-layer-architecture)

**SkillOpt Engine** is a 100% local, self-improving AI software engineering stack running natively on Apple Silicon. It combines **Dual-Layer Activation Steering**, **Logit-Level Grammar Masking**, **Multi-Agent Planning**, and a **Graph-Based DPO Preference Flywheel**.

---

## 🏛️ System Architecture

```text
                  ┌──────────────────────────────────────────────────────────┐
                  │              Dual-Layer Steering Engine                  │
                  └────────────────────────────┬─────────────────────────────┘
                                               │
               ┌───────────────────────────────┴───────────────────────────────┐
               ▼                                                               ▼
 ┌────────────────────────────┐                                 ┌────────────────────────────┐
 │ Layer 1: Steering Vectors  │                                 │ Layer 2: GBNF Logit Fences │
 │ (Contrastive Activation)   │                                 │ (Grammar-Constrained Tokens)│
 └────────────────────────────┘                                 └────────────────────────────┘
               │                                                               │
               └───────────────────────────────┬───────────────────────────────┘
                                               ▼
                                 ┌───────────────────────────┐
                                 │ Multi-Agent Orchestrator  │
                                 │ (Gemma-4 Plan / Ornith Code)│
                                 └─────────────┬─────────────┘
                                               ▼
                                 ┌───────────────────────────┐
                                 │  MCTS DPO Flywheel        │
                                 │  (py_compile / unittest)  │
                                 └───────────────────────────┘
```

---

## 📊 Benchmark Results

Reproducible performance metrics running locally on Apple Silicon GPU (`run_benchmarks.py`):

| Benchmark Metric | Result | Status |
|---|---|---|
| **Compilation Pass Rate** | `100.0%` (35/35 workspace Python files) | ✅ PASSED |
| **MCP Scaffold Build & Test Latency** | `0.02 seconds` | ✅ PASSED |
| **DPO Verified Preference Pair Yield** | `2 Pairs Logged` (`dpo_graph_dataset.jsonl`) | ✅ ACTIVE |
| **Local Inference Server Latency** | `< 2.5 ms` (`AtomicChat/Ornith-9B-MLX-6bit`) | ✅ ONLINE |

---

## ⚡ Quick Start & Usage

### 1. Install & Setup
```bash
git clone https://github.com/your-username/skillopt-engine.git
cd skillopt-engine
pip install -r requirements.txt
```

### 2. Run the Unified Master CLI
```bash
# Sync prompt guidelines directly into Cursor IDE and Antigravity agents
python3 skillopt_engine_cli.py sync

# Scaffold and verify a new Model Context Protocol (MCP) server
python3 skillopt_engine_cli.py mcp my_calculator

# Run Gemma-4 (Planner) + Ornith (Coder) task routing
python3 skillopt_engine_cli.py orchestrate "Build a Python CLI for string utilities"

# Run Graph-Based DPO Candidate Search & LoRA Fine-Tuning Pass
python3 skillopt_engine_cli.py self-improve "Write a palindrome checker with type hints."

# Run workspace health check across all Python files
python3 skillopt_engine_cli.py health
```

---

## 📜 License
Distributed under the MIT License. See `LICENSE` for more information.
