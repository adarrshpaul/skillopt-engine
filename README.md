# SkillOpt Engine

The SkillOpt Engine is a disciplined, Claude Code Harness-inspired governance framework for multi-agent coding workflows. It provides strict routing, safety guarantees, and evidentiary test pipelines for running local AI models on hardware-constrained systems, specifically targeting Apple Silicon with a strict **16GB RAM limit**.

## The Novel Intention
The core thesis of the SkillOpt Engine is that **we can achieve SWE-bench level multi-agent reasoning on consumer hardware (16GB RAM) without sacrificing context or model capability.** 
Instead of relying on cloud APIs or attempting to load massive models concurrently (which causes catastrophic disk swapping and freezes), SkillOpt uses a highly orchestrated **Maker-Checker ping-pong architecture**. It systematically spins up, queries, and evicts large models (Ling-mini-2.0 and Ornith-9B) sequentially in the same shared memory space, achieving enterprise-grade multi-agent reasoning entirely locally.

---

## Core Architecture

### 1. The Orchestrator (`orchestrator.py`)
- **Heterogeneous Multi-Agent Routing**: Uses distinct, specialized models for each agent role via configurable environment variables:
  - **Planner** (`PLANNER_MODEL`): Decomposes user goals into structured JSON task graphs. Default: `nvidia/nemotron-3-ultra-550b-a55b:free` via OpenRouter.
  - **Coder** (`CODER_MODEL`): Executes an iterative ReAct loop (up to 15 steps) with tool access to write files, run commands, and navigate the workspace. Default: `poolside/laguna-s-2.1:free`.
  - **Reviewer** (`REVIEWER_MODEL`): Performs severity-tiered code review (CRITICAL/MAJOR/MINOR/RECOMMENDATION) and gates task completion. Default: `nvidia/nemotron-3-super-120b-a12b:free`.
- **Multi-Engine Backend**: Supports `mlx`, `openrouter`, `openai`, `litellm`, and `ollama` engines simultaneously.
- **Session Ledger (`core/session_ledger.py`)**: Append-only JSONL event log that deterministically projects model context via `derive_messages()`. Every tool call, model response, review verdict, and error is immutably recorded.

### 2. Intelligent Failover Architecture
- **Cloud → Local Hot-Swap**: When OpenRouter returns `429 Too Many Requests` or `402 Payment Required`, the orchestrator instantly hot-swaps the request to a local MLX model (`mlx-community/Nanbeige4.1-3B-heretic-4bit`) with zero queuing delay.
- **Atomic Plan Synthesis**: If the Planner cannot decompose a goal into JSON subtasks after 3 feedback-driven retries, the system automatically synthesizes a default atomic task graph from the user's goal, ensuring the Coder agent always has work to execute.

### 3. Resilient Output Parsing (`core/output_extractor.py`)
- **Multi-Strategy JSON Extraction**: Handles direct JSON, markdown code fences, conversational preambles, and nested bracket structures via a 4-stage extraction pipeline:
  1. Direct `json.loads()` attempt
  2. Markdown fence regex extraction
  3. Bracket-depth counting with string-literal awareness
  4. Scanning `json.JSONDecoder.raw_decode()` fallback

### 4. Feedback-Driven Recovery
- **Planner Retry Loop**: On JSON parse failure, the orchestrator re-prompts the Planner with an explicit corrective instruction and a concrete format example (up to 3 attempts).
- **Multi-Turn Self-Healing**: When the Reviewer rejects code, the Coder receives the review feedback and iterates up to 3 repair cycles with re-review after each attempt.

### 5. Instruction Governance (`core/instruction_governance.py`)
- **Reporails-Native Linter**: A deterministic rule engine (inspired by [Reporails CLI](https://github.com/reporails/cli)) that validates user goals against mechanical rules before execution:
  - Blocks vague, overly broad, or dangerous instructions.
  - Enforces specificity in file targets and scope.
  - Runs without any external API dependency.

### 6. Sandbox Execution Environment (`sandbox/venv_executor.py`)
- **Native Venv Isolation**: Uses Python virtual environments (`venv`) with PTY-based subprocess execution for full terminal fidelity.
- **Background Task Management**: Supports daemon processes via threaded output streaming.
- **Process Group Cleanup**: Uses `os.killpg()` for clean teardown of entire process trees.

---

## Safety & Security

1. **Path Traversal Protection**: `_safe_path()` validates all file operations against the workspace boundary using trailing-separator-aware `startswith()` checks, preventing sibling directory escapes.
2. **Command Safety Gate (`core/safety_gate.py`)**: Blocks dangerous shell commands (`rm -rf /`, `curl | bash`, etc.) before sandbox execution.
3. **Tool Registry**: All 9 tools (`run_command`, `bash`, `write_file`, `edit_file`, `replace_file_content`, `read_file`, `list_dir`, `manage_task`, `update_plan`) are centrally registered with unified safety enforcement.
4. **DPO Deduplication**: The reporter engine strips hex, UUID, and path data from raw crashes, generating deterministic structural hashes to prevent dataset pollution.

---

## Supported Free Models (OpenRouter)

The following free-tier models are tested and supported via the heterogeneous routing architecture:

| Model | Best Role | Context | Key Strength |
|-------|-----------|---------|--------------|
| `nvidia/nemotron-3-ultra-550b-a55b:free` | Planner | 1M | Multi-step reasoning, orchestration |
| `poolside/laguna-s-2.1:free` | Coder | 262K | 70.2% Terminal-Bench, agentic coding |
| `nvidia/nemotron-3-super-120b-a12b:free` | Reviewer | 262K | Fast MoE, high accuracy |
| `cohere/north-mini-code:free` | Coder (alt) | 256K | Terminal tasks, agent harnesses |
| `dots-studio/dots-3-note-preview:free` | Planner (alt) | 512K | Coding, multi-step workflows |
| `openai/gpt-oss-20b:free` | Reviewer (alt) | 131K | Function calling, structured output |

**Local Fallback**: `mlx-community/Nanbeige4.1-3B-heretic-4bit` via Apple MLX (zero-latency failover)

---

## Getting Started

### Prerequisites
- macOS (Apple Silicon optimized, 16GB RAM strict limit)
- Python 3.11+
- `uv` or `pip` for dependency management
- An [OpenRouter API key](https://openrouter.ai/) (free tier supported)

### Installation
```bash
# Clone the repository
git clone https://github.com/adarrshpaul/skillopt-engine.git
cd skillopt-engine

# Create virtual environment
python3 -m venv tb-env
source tb-env/bin/activate

# Install dependencies
pip install pytest psutil anyio python-dotenv faiss-cpu sentence-transformers

# Set your OpenRouter API key
echo "OPENROUTER_API_KEY=sk-or-..." > .env
```

### Running the Orchestrator
```bash
# Configure models in run_tests.sh, then:
source tb-env/bin/activate
./run_tests.sh

# Or run directly:
python3 -u orchestrator.py "Your coding goal here"
```

### Environment Variables
```bash
# Model routing (set per role)
export PLANNER_ENGINE="openrouter"
export PLANNER_URL="https://openrouter.ai/api/v1"
export PLANNER_MODEL="nvidia/nemotron-3-ultra-550b-a55b:free"

export CODER_ENGINE="openrouter"
export CODER_URL="https://openrouter.ai/api/v1"
export CODER_MODEL="poolside/laguna-s-2.1:free"

export REVIEWER_ENGINE="openrouter"
export REVIEWER_URL="https://openrouter.ai/api/v1"
export REVIEWER_MODEL="nvidia/nemotron-3-super-120b-a12b:free"
```

---

## Project Structure
```
├── orchestrator.py              # Main multi-agent ReAct orchestrator
├── model_router.py              # Engine/model routing configuration
├── run_tests.sh                 # Test harness entry point
├── core/
│   ├── output_extractor.py      # Resilient JSON extraction from LLM output
│   ├── instruction_governance.py # Reporails-native goal linting
│   ├── session_ledger.py        # Append-only JSONL event ledger
│   ├── task_ledger.py           # Markdown task tracking (Plans.md)
│   ├── tool_pipeline.py         # Multi-grammar tool call parser
│   ├── safety_gate.py           # Command safety evaluation
│   └── compaction.py            # Context window compaction governor
├── sandbox/
│   └── venv_executor.py         # PTY-based venv sandbox executor
├── benchmark_free_models.py     # Free-tier model benchmark suite
├── STRICT_RULES.md              # Instruction governance ruleset
└── SYSTEM_ARCHITECTURE.md       # Detailed architecture documentation
```

---

## License
Apache 2.0
