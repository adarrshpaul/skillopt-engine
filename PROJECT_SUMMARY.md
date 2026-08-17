# SkillOpt Engine — Project Summary

**SkillOpt Engine** is a hybrid local/cloud self-improving AI software engineering stack. It combines:

- Multi-agent planning & delegation (Architect, Developer, Reviewer) via CrewAI-inspired YAML configurations.
- 5-Tier Resilient Model Cascade (Google, Mistral, Groq, OpenRouter, MLX) for guaranteed uptime.
- Two-Tier Context Compaction & Cognitive Memory to maximize context window utility.
- Dual-layer activation steering (CAA vectors + GBNF logit fences) for local Apple Silicon models.
- A graph-based DPO preference flywheel (MCTS → preference pairs → LoRA).
- MCP server scaffolding and IDE guideline sync.

Primary docs: [README.md](README.md), [SYSTEM_ARCHITECTURE.md](SYSTEM_ARCHITECTURE.md), [PROJECT.md](PROJECT.md), [STRICT_RULES.md](STRICT_RULES.md).

---

## Master entrypoints

| Entrypoint | Role |
|---|---|
| [`skillopt_engine_cli.py`](skillopt_engine_cli.py) | Unified CLI: `sync`, `mcp`, `orchestrate`, `self-improve`, `health` |
| [`dashboard_server.py`](dashboard_server.py) | Web cockpit + REST API on port **8900** |
| [`run_benchmarks.py`](run_benchmarks.py) | AST / MCP / latency / API verification suite |
| [`auto_coder.py`](auto_coder.py) | Codebase health inspector |
| [`orchestrator.py`](orchestrator.py) | The core 15-step ReAct loop and multi-agent routing entrypoint |

---

## Core subsystems

```text
CLI (skillopt_engine_cli) ──► Orchestrator ──┐
                           ──► DPO Flywheel ──┼──► Inference :8800 (Local) / Cloud APIs
Dashboard :8900 ──► Dual-Layer Steering ─────┘
```

- **Orchestration** — [`orchestrator.py`](orchestrator.py): Uses `config/agents.yaml` for dynamic routing across cloud API fallbacks (Google/Mistral/Groq). Agents emit XML-style tool calls validated by a strict AST semantic checker and executed in `venv_executor.py`. Includes `CognitiveMemory` for cross-session insight tracking.
- **Steering** — [`steer_compile.py`](steer_compile.py) builds vectors from [`skills/*.md`](skills/); [`steer_server.py`](steer_server.py) applies them on residual-stream hooks (port 8800) for local MLX models. *Note: Cloud API fallback does not support CAA steering vectors yet.*
- **DPO flywheel** — [`dpo_tree_generator.py`](dpo_tree_generator.py) MCTS sandbox → `dpo_graph_dataset.jsonl`; [`dpo_train.py`](dpo_train.py) LoRA on MLX → `dpo_adapters/`.
- **MCP** — [`mcp_builder.py`](mcp_builder.py) scaffolds MCP servers + unittests.
- **IDE sync** — trainer syncs guidelines into `.cursorrules` and `.agents/rules/`.

---

## Where model cards come from

### UI cards (frontend-defined)

In [`dashboard_ui.html`](dashboard_ui.html) (L639–L670), four sidebar cards are hardcoded for the local path:

| UI key | Display |
|---|---|
| `ling-3.0-flash` | Ling-3.0-Flash — 124B Sparse MoE (5.1B active) |
| `nanbeige-3b` | Nanbeige 4.2-3B — Looped Transformer |
| `gemma-4-12b` | Gemma 4 12B — Encoder-Free Multimodal |
| `ornith-9b` | Ornith 1.0-9B — Apple Silicon MLX Offline |

### Backend registry (all point at one local weight)

In [`harness_v2.py`](harness_v2.py), `ModelRegistry.MODELS` maps those keys to `ModelProfile`s. Every profile uses:

`LOCAL_MODEL_PATH = "/Users/adarrsh/workspace/models/fused-gemma"`

Display names / architectures / simulated latency differ per card; the on-disk model does not. The orchestrator now supplements these local mocks with real Cloud API fallback cascading.

### Actual inference

- **Weights (Local):** `/Users/adarrsh/workspace/models/fused-gemma` (~5.1 GB safetensors)
- **Server (Local):** `mlx_lm.server` (or `steer_server.py` per architecture docs) on `http://localhost:8800`
- **Cloud Fallback:** Routes through standard `urllib` / HTTP requests with `.env` API keys (Google Gemini, Mistral, Groq, OpenRouter).

---

## Workspace conventions & coordination

- [PROJECT.md](PROJECT.md): Maker-Checker, offline MLX, sandboxed shell, `py_compile` / pytest.
- [CONTEXT.md](CONTEXT.md) / [.tasks/](.tasks/): multi-agent task queue; sibling projects Machine (IMS/OKF) and Siemens iX MCP live outside this repo but share coordination.
- [skills/](skills/): steerable skill markdown → compiled `.pt` vectors (`strict_json`, `concise_response`, `no_apologies`, `code_only`).

---

## Reported local benchmarks (from README)

- 100% `py_compile` pass on workspace Python files
- MCP scaffold latency ~0.02s
- DPO preference pairs logged to `dpo_graph_dataset.jsonl`
- Local inference latency claimed < 2.5 ms on Ornith-class MLX path
- Cloud orchestrator resilience: 0-downtime execution verified via 47+ automated unit tests.

---

## Bottom line

This workspace is a hybrid local/cloud coding-agent cockpit. While local UI model cards operate against one fused-gemma weight via MLX, the real power lies in the orchestrator's cloud API cascade, declarative CrewAI-inspired agent configs, and cognitive memory framework. The platform stitches orchestration, steering, MCP scaffolding, and DPO self-improvement into one robust software engineering stack.
