# SkillOpt Engine

SkillOpt Engine is a production-grade multi-agent coding harness and orchestration framework designed for Apple Silicon (macOS) and OpenRouter free-tier models. It combines heterogeneous role specialization, intelligent hot-swap failover (model cascading), resilient multi-grammar tool extraction, sandbox execution, and deterministic instruction governance.

---

## 🏛️ System Architecture

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

---

## 🔍 Model Roles & Ground-Truth Configuration

### 1. Primary: Cloud API Mode (OpenRouter Free Tier)
When running in cloud mode (configured in `run_tests.sh`), the orchestrator partitions duties across specialized models:

| Agent Role | Model ID | Context | Description & Responsibility |
|---|---|---|---|
| **Planner** | `nvidia/nemotron-3-ultra-550b-a55b:free` | 1M tokens | High-level reasoning and task graph decomposition into JSON subtasks. |
| **Coder** | `poolside/laguna-s-2.1:free` | 262K tokens | Code generation and tool execution inside a 15-step iterative ReAct loop. |
| **Reviewer** | `nvidia/nemotron-3-super-120b-a12b:free` | 262K tokens | Severity-tiered code review (`CRITICAL`, `MAJOR`, `MINOR`, `RECOMMENDATION`). |

### 2. Local Fallback & Offline Engines (Apple Silicon)
- **Local MLX Server (`http://127.0.0.1:8801/v1`)**: Runs `mlx-community/Nanbeige4.1-3B-heretic-4bit` natively on Apple Silicon Metal GPU. Provides zero-latency hot-swap failover whenever cloud endpoints return `429 Too Many Requests` or `402 Payment Required`.
- **Local Ollama Server (`http://127.0.0.1:11434`)**: Hosts `ornith9b:latest` (6.5 GB) for offline development.

---

## 🔄 End-to-End Execution Lifecycle

```mermaid
sequenceDiagram
    autonumber
    actor User
    participant Gov as Reporails Linter
    participant Planner as Planner (Nemotron 550B)
    participant Coder as Coder ReAct (Laguna S)
    participant Tools as Tool Registry & Sandbox
    participant Reviewer as Reviewer (Nemotron 120B)
    participant Ledger as Session Ledger (JSONL)

    User->>Gov: Submit Goal
    Gov->>Gov: Lint against STRICT_RULES.md
    Gov->>Planner: Validated Goal
    Planner->>Ledger: Emit task_graph.json (subtasks)
    loop Each Planned Subtask
        loop ReAct Step (up to 15 iterations)
            Coder->>Tools: Emit <execute>tool(args)</execute>
            Tools->>Tools: Validate _safe_path & execute in .test_venv
            Tools-->>Coder: Tool Output (Compressed)
            Coder->>Ledger: Log tool/call & tool/result
        end
        Coder->>Reviewer: Target file code & completion signal <done>
        Reviewer->>Reviewer: Deterministic AST check & semantic review
        alt APPROVE (or MINOR)
            Reviewer->>Ledger: Log review/result (PASSED)
        else REQUEST_CHANGES (CRITICAL / MAJOR)
            Reviewer->>Coder: Feedback critique (Self-Healing Loop up to 3x)
            Coder->>Tools: write_file patch
        end
    end
```

---

## 🛠️ Core Harness Modules

### 1. Resilient Output Parsing (`core/output_extractor.py`)
LLMs often emit conversational preambles or messy formatting when asked for JSON. The 4-stage extractor ensures zero-crash parsing:
1. **Direct Parse**: `json.loads(text.strip())`
2. **Markdown Block Extraction**: Regex extraction from ` ```json ... ``` ` or ` ``` ... ``` ` blocks.
3. **Bracket Balance Counting**: State machine that tracks bracket depth while ignoring string literals and escapes.
4. **Scanning Decoder Fallback**: `json.JSONDecoder().raw_decode()` across all bracket positions.

### 2. Feedback-Driven Recovery & Plan Synthesis
- **Planner Retry Loop**: If a model generates malformed task graph output, the orchestrator re-prompts with explicit format instructions (up to 3 attempts).
- **Atomic Plan Synthesis**: If planner decomposition is exhausted, the harness synthesizes a 1-step atomic plan from the goal so the Coder agent can proceed immediately.
- **Multi-Turn Self-Healing**: Reviewer rejections trigger an iterative 3-turn repair cycle with the Coder rather than abandoning the task.

### 3. Tool Pipeline & Sandbox Execution (`sandbox/venv_executor.py`)
All actions run through a unified `ToolRegistry` with path traversal defense:
- **`run_command(cmd, is_daemon)` / `bash`**: Runs shell commands inside `.test_venv` with PTY support.
- **`manage_task(action, task_id)`**: Inspects or terminates background daemon tasks.
- **`write_file(path, content)`**: Atomically writes workspace files.
- **`replace_file_content(path, start_line, end_line, content)` / `edit_file`**: Surgically replaces 1-indexed line ranges.
- **`read_file(path)`**: Reads files with automatic head/tail truncation for large files (>4000 chars).
- **`list_dir(path)`**: Lists workspace directory structures.
- **`update_plan(new_tasks)`**: Dynamically updates remaining subtasks and synchronizes `Plans.md`.

### 4. Instruction Governance (`core/instruction_governance.py`)
Evaluates prompts against `STRICT_RULES.md` before execution:
- Blocks overly broad or ambiguous instructions.
- Enforces explicit file targeting.
- Flags destructive commands before they reach execution.

### 5. Append-Only Session Ledger (`core/session_ledger.py`)
Records all events into `runs/session_<id>.jsonl`:
- `goal/start`: Initial prompt and hyperparameters.
- `turn/start`, `step/start`: Subtask and ReAct step markers.
- `tool/call`, `tool/result`, `tool/error`: Complete tool inputs and outputs.
- `review/result`: Reviewer verdicts and critique feedback.

---

## ⚖️ Honest Benchmark Comparison: SkillOpt vs Claude Code vs DeepSeek Harness

To assess the engineering quality and real-world capabilities of SkillOpt Engine, here is an honest, objective breakdown comparing our architecture against the **Claude Code Harness** (Anthropic) and **DeepSeek SWE-bench Harness** (DeepSeek/OpenCode).

### 📊 Capability Matrix

| Architectural Feature | SkillOpt Engine | Claude Code Harness | DeepSeek Harness |
|---|---|---|---|
| **Heterogeneous Model Cascading** | ✅ **Native Cloud-to-Local Hot-Swap** (OpenRouter 429 → Local MLX) | ❌ Single-vendor closed API (Claude only) | ❌ Single-model focus (DeepSeek API/Self-hosted) |
| **Hardware Cost & Accessibility** | ✅ **$0 / Zero-Cost** (Free-tier models + Local Apple Silicon) | ❌ High API cost ($20-$100+/mo for heavy usage) | ❌ High GPU VRAM requirements for self-hosting (70B/671B) |
| **Deterministic Instruction Governance** | ✅ **Reporails-Native Linter** (Pre-execution rule enforcement) | ⚠️ Post-hoc prompt guardrails | ⚠️ Basic system prompt instructions |
| **Append-Only Telemetry Ledger** | ✅ **Deterministic JSONL Event Replay** (`derive_messages`) | ✅ Full session replay & telemetry | ✅ Trajectory rollout logging |
| **Tool Extraction Robustness** | ✅ **4-Stage Multi-Grammar Extractor** (Bracket state machine) | ✅ Native JSON Function Calling API | ⚠️ Tag parsing (`<tool_call>` / XML) |
| **Context Window Compaction** | ⚠️ Static Compaction Governor (Triggered per subtask) | ✅ **Dynamic Sliding-Window Compaction** + Prompt Caching | ⚠️ Chunked trajectory truncation |
| **Codebase Structural Indexing** | ⚠️ P3 FAISS (Optional, disabled on 16GB mode) | ✅ **Full LSP, AST Indexing, & Ripgrep Pipes** | ✅ Tree-sitter AST Symbol Graph Search |
| **Terminal / PTY Interactivity** | ⚠️ Native Venv PTY (Buffered execution) | ✅ **True Bi-directional Streaming PTY** | ⚠️ Non-interactive Docker subprocesses |
| **Raw Reasoning Ceiling** | ⚠️ Dependent on Free/Small Models (3B - 550B MoE) | ✅ **Frontier-Class Reasoning** (Claude 3.7 Sonnet) | ✅ **Frontier-Class Reasoning** (DeepSeek-V3 / R1) |

---

### 🔍 Deep-Dive: Where We Win vs Where We Have Gaps

#### 🏆 Where SkillOpt Excels
1. **Free-Tier Resilience & Hot-Swap Failover**: Neither Claude Code nor DeepSeek harnesses are designed to survive rate limits on $0 free tiers. SkillOpt automatically intercepts 429/402 HTTP errors and hot-swaps to local Apple Silicon MLX without dropping task state.
2. **Deterministic Pre-Execution Linting**: Our Reporails-inspired linter evaluates user intent against mechanical rules (`STRICT_RULES.md`) *before* spending tokens or dispatching to models.
3. **Low-Memory Apple Silicon Optimization**: Runs comfortably on 16GB MacBooks using 4-bit MLX weights without requiring heavy container VMs or multi-GPU clusters.

#### ⚠️ Honest Gaps & Future Roadmap
1. **Model Intelligence Floor**: When free cloud models hit aggressive rate limits, failing over to local 3B models (`Nanbeige 4.1 3B`) limits planning capacity for large 50+ file codebases. Frontier closed models (Claude 3.7 / DeepSeek R1) inherently handle complex multi-file dependencies better.
2. **Context Compaction inside ReAct**: Claude Code dynamically compacts conversation turns mid-session using prompt caching. SkillOpt's `CompactionGovernor` currently runs between subtasks rather than dynamically compressing inside the 15-step ReAct loop.
3. **Semantic Symbol Search**: DeepSeek and Claude Code utilize Tree-sitter AST search and Language Server Protocols (LSP) to resolve cross-file references. SkillOpt currently relies on lexical tools (`read_file`, `list_dir`) and optional FAISS embeddings.

---

## 🚀 Quickstart & Setup

### Prerequisites
- macOS with Apple Silicon (M1/M2/M3/M4)
- Python 3.11+
- Virtual environment `tb-env`

### Installation & Execution
```bash
# 1. Clone repository
git clone https://github.com/adarrshpaul/skillopt-engine.git
cd skillopt-engine

# 2. Activate virtual environment
source tb-env/bin/activate

# 3. Install dependencies
pip install pytest psutil anyio python-dotenv faiss-cpu sentence-transformers

# 4. Set OpenRouter API Key (in .env or environment)
export OPENROUTER_API_KEY="sk-or-v1-..."

# 5. Run test runner
./run_tests.sh

# Or run orchestrator with custom goal
python3 -u orchestrator.py "Create a math helper utility in math_helper.py and verify with pytest"
```

---

## ⚙️ Environment Configuration

| Variable | Default | Description |
|---|---|---|
| `PLANNER_MODEL` | `nvidia/nemotron-3-ultra-550b-a55b:free` | Model used for task decomposition |
| `PLANNER_ENGINE` | `openrouter` | Engine for Planner (`openrouter`, `mlx`, `ollama`, `litellm`) |
| `PLANNER_URL` | `https://openrouter.ai/api/v1` | Endpoint URL for Planner |
| `CODER_MODEL` | `poolside/laguna-s-2.1:free` | Model used for coding and tool execution |
| `CODER_ENGINE` | `openrouter` | Engine for Coder |
| `CODER_URL` | `https://openrouter.ai/api/v1` | Endpoint URL for Coder |
| `REVIEWER_MODEL` | `nvidia/nemotron-3-super-120b-a12b:free` | Model used for code review |
| `REVIEWER_ENGINE` | `openrouter` | Engine for Reviewer |
| `REVIEWER_URL` | `https://openrouter.ai/api/v1` | Endpoint URL for Reviewer |
| `FALLBACK_MODEL` | `mlx-community/Nanbeige4.1-3B-heretic-4bit` | Local model for hot-swap failover |
| `FALLBACK_ENGINE` | `mlx` | Engine for fallback |
| `FALLBACK_URL` | `http://localhost:8801/v1` | Local MLX server URL |
| `OPENROUTER_API_KEY` | *(None)* | OpenRouter API authentication key |

---

## 🧪 Running Tests

```bash
# Run unit test suite across all core modules
pytest tests/ -v

# Run individual module tests
pytest tests/test_tool_pipeline.py
pytest tests/test_safety_gate.py
pytest tests/test_session_ledger.py
pytest tests/test_task_ledger.py
pytest tests/test_compaction.py
pytest tests/test_parallel_executor.py
```

---

## 📁 Repository Directory Map

```
├── orchestrator.py              # Main multi-agent ReAct orchestrator
├── model_router.py              # Role-to-endpoint routing registry
├── run_tests.sh                 # Test runner entrypoint
├── core/
│   ├── output_extractor.py      # Resilient JSON array and object extraction
│   ├── instruction_governance.py# Reporails-native goal linter
│   ├── session_ledger.py        # Append-only JSONL execution ledger
│   ├── task_ledger.py           # Markdown task state tracker (Plans.md)
│   ├── tool_pipeline.py         # Multi-grammar tool parsing engine
│   ├── safety_gate.py           # Command validation floor
│   ├── parallel_executor.py     # Concurrent tool execution engine
│   └── compaction.py            # Context window compaction governor
├── sandbox/
│   └── venv_executor.py         # PTY-based venv execution sandbox
├── tests/                       # Unit test suite for core modules
├── benchmark_free_models.py     # OpenRouter model evaluation suite
├── STRICT_RULES.md              # Instruction governance ruleset
└── SYSTEM_ARCHITECTURE.md       # Architectural deep-dive
```

---

## License
Apache 2.0
