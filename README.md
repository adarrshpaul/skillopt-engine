# SkillOpt Engine

SkillOpt Engine is an agentic coding harness and multi-agent orchestrator optimized for Apple Silicon and OpenRouter free-tier models. It features heterogeneous role routing, intelligent failover (model cascading), resilient output extraction, and safety governance.

---

## 🔍 Model Inventory & Ground-Truth Configuration

Here is the exact model setup used by the system:

```
                               ┌──────────────────────────────────────────────┐
                               │           Multi-Agent Orchestrator           │
                               │              (orchestrator.py)               │
                               └──────────────────────┬───────────────────────┘
                                                      │
                       ┌──────────────────────────────┴──────────────────────────────┐
                       ▼                                                             ▼
         ┌───────────────────────────┐                                 ┌───────────────────────────┐
         │  Primary: Cloud API Mode  │                                 │   Fallback / Local Mode   │
         │       (OpenRouter)        │                                 │     (Apple MLX & Ollama)  │
         └─────────────┬─────────────┘                                 └─────────────┬─────────────┘
                       │                                                             │
        ┌──────────────┼──────────────┐                               ┌──────────────┴──────────────┐
        ▼              ▼              ▼                               ▼                             ▼
   ┌─────────┐    ┌─────────┐    ┌──────────┐                 ┌───────────────┐             ┌───────────────┐
   │ Planner │    │  Coder  │    │ Reviewer │                 │   Local MLX   │             │ Local Ollama  │
   │Nemotron │    │ Laguna  │    │ Nemotron │                 │  (Port 8801)  │             │ (Port 11434)  │
   │  550B   │    │  S 2.1  │    │120B Super│                 │Nanbeige 4.1 3B│             │   Ornith 9B   │
   └─────────┘    └─────────┘    └──────────┘                 └───────────────┘             └───────────────┘
```

### 1. Primary: Cloud API Mode (OpenRouter Free Tier)
When running in cloud mode (configured in `run_tests.sh`), the orchestrator splits responsibilities across 3 specialized models:
- **Planner (`PLANNER_MODEL`)**: `nvidia/nemotron-3-ultra-550b-a55b:free` (1M context) — Decomposes high-level goals into atomic execution tasks.
- **Coder (`CODER_MODEL`)**: `poolside/laguna-s-2.1:free` (262K context) — Generates code and executes tool actions in a ReAct loop.
- **Reviewer (`REVIEWER_MODEL`)**: `nvidia/nemotron-3-super-120b-a12b:free` (262K context) — Inspects produced code and gates task completion.

### 2. Fallback / Local Mode (Apple Silicon)
- **Local MLX Engine (Port 8801)**: Runs `mlx-community/Nanbeige4.1-3B-heretic-4bit`. Used as the zero-latency hot-swap target when OpenRouter returns `429 Too Many Requests` or `402 Payment Required`.
- **Local Ollama Engine (Port 11434)**: Runs `ornith9b:latest` (6.5 GB). Available for 100% offline local development.

---

## 🛠️ Core Engine Components

### 1. Orchestrator ReAct Loop (`orchestrator.py`)
- **Outer Task Graph Loop**: Iterates through planned subtasks sequentially.
- **Inner ReAct Step Loop**: Runs up to 15 iterations per subtask. Context is reconstructed strictly from the append-only event ledger via `derive_messages()`.
- **Atomic Plan Synthesis**: If planner decomposition fails after 3 feedback attempts, the engine synthesizes an atomic single-task execution plan to ensure the Coder agent can proceed.

### 2. Resilient Output Parsing (`core/output_extractor.py`)
Multi-stage fallback extractor that handles noisy, non-deterministic model outputs:
1. Direct `json.loads()`
2. Markdown code block regex (` ```json ... ``` `)
3. Outermost bracket-depth tracking (aware of string literals and escape characters)
4. Streaming `json.JSONDecoder.raw_decode()`

### 3. Tool Pipeline & Sandbox
- **Tool Registry**: Centrally dispatches 9 tools: `run_command`, `bash`, `write_file`, `edit_file`, `replace_file_content`, `read_file`, `list_dir`, `manage_task`, `update_plan`.
- **Sandbox Executor (`sandbox/venv_executor.py`)**: Runs commands inside a dedicated `.test_venv` virtual environment with PTY support for terminal fidelity and background task tracking.
- **Security Gate**: `_safe_path()` enforces workspace boundary containment to prevent directory traversal escapes. `core/safety_gate.py` denies dangerous shell patterns.

### 4. Instruction Governance (`core/instruction_governance.py`)
- **Native Linter**: Deterministically checks goals against rules (defined in `STRICT_RULES.md`) before running to prevent vague instructions, excessive scope, or forbidden commands.

---

## 🚀 Quickstart

### Prerequisites
- macOS on Apple Silicon (M-series)
- Python 3.11+
- Virtual environment `tb-env`

### Setup & Run
```bash
# 1. Activate virtual environment
source tb-env/bin/activate

# 2. Configure environment (e.g. OpenRouter API Key)
export OPENROUTER_API_KEY="your-key-here"

# 3. Run test harness
./run_tests.sh
```

---

## 📁 Repository Map

```
├── orchestrator.py              # Multi-agent ReAct orchestrator
├── model_router.py              # Role-to-endpoint routing registry
├── run_tests.sh                 # Test runner entrypoint
├── core/
│   ├── output_extractor.py      # Resilient JSON array and object extraction
│   ├── instruction_governance.py# Reporails-native goal linter
│   ├── session_ledger.py        # Append-only JSONL execution ledger
│   ├── task_ledger.py           # Markdown task state tracker (Plans.md)
│   ├── tool_pipeline.py         # Multi-grammar tool parsing engine
│   ├── safety_gate.py           # Command validation floor
│   └── compaction.py            # Context window compaction governor
├── sandbox/
│   └── venv_executor.py         # PTY-based venv execution sandbox
├── benchmark_free_models.py     # OpenRouter model evaluation suite
└── STRICT_RULES.md              # Instruction governance rules
```

---

## License
Apache 2.0
