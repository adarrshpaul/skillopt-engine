# SkillOpt Engine — Project Summary

**SkillOpt Engine** is a 100% local, self-improving AI software engineering stack for Apple Silicon. It combines:

- Dual-layer activation steering (CAA vectors + GBNF logit fences)
- Multi-agent planning (planner + coder routing)
- A graph-based DPO preference flywheel (MCTS → preference pairs → LoRA)
- MCP server scaffolding and IDE guideline sync

Primary docs: [README.md](README.md), [SYSTEM_ARCHITECTURE.md](SYSTEM_ARCHITECTURE.md), [PROJECT.md](PROJECT.md), [STRICT_RULES.md](STRICT_RULES.md).

---

## Master entrypoints

| Entrypoint | Role |
|---|---|
| [`skillopt_engine_cli.py`](skillopt_engine_cli.py) | Unified CLI: `sync`, `mcp`, `orchestrate`, `self-improve`, `health` |
| [`dashboard_server.py`](dashboard_server.py) | Web cockpit + REST API on port **8900** |
| [`run_benchmarks.py`](run_benchmarks.py) | AST / MCP / latency / API verification suite |
| [`auto_coder.py`](auto_coder.py) | Codebase health inspector |

---

## Core subsystems

```text
CLI (skillopt_engine_cli) ──► Orchestrator ──┐
                           ──► DPO Flywheel ──┼──► Inference :8800
Dashboard :8900 ──► Dual-Layer Steering ─────┘
```

- **Orchestration** — [`orchestrator.py`](orchestrator.py): Gemma-4 plans in JSON; Ornith-9B codes; `py_compile` self-correction loop.
- **Steering** — [`steer_compile.py`](steer_compile.py) builds vectors from [`skills/*.md`](skills/); [`steer_server.py`](steer_server.py) applies them on residual-stream hooks (port 8800).
- **DPO flywheel** — [`dpo_tree_generator.py`](dpo_tree_generator.py) MCTS sandbox → `dpo_graph_dataset.jsonl`; [`dpo_train.py`](dpo_train.py) LoRA on MLX → `dpo_adapters/`.
- **MCP** — [`mcp_builder.py`](mcp_builder.py) scaffolds MCP servers + unittests.
- **IDE sync** — trainer syncs guidelines into `.cursorrules` and `.agents/rules/`.

---

## Where model cards come from

### UI cards (frontend-defined)

In [`dashboard_ui.html`](dashboard_ui.html) (L639–L670), four sidebar cards are hardcoded:

| UI key | Display |
|---|---|
| `ling-3.0-flash` | Ling-3.0-Flash — 124B Sparse MoE (5.1B active) |
| `nanbeige-3b` | Nanbeige 4.2-3B — Looped Transformer |
| `gemma-4-12b` | Gemma 4 12B — Encoder-Free Multimodal |
| `ornith-9b` | Ornith 1.0-9B — Apple Silicon MLX Offline |

### Backend registry (all point at one local weight)

In [`harness_v2.py`](harness_v2.py) (L58–L99), `ModelRegistry.MODELS` maps those keys to `ModelProfile`s. Every profile uses:

`LOCAL_MODEL_PATH = "/Users/adarrsh/workspace/models/fused-gemma"`

Display names / architectures / simulated latency differ per card; the on-disk model does not.

### Actual inference

- **Weights:** `/Users/adarrsh/workspace/models/fused-gemma` (~5.1 GB safetensors)
- **Server:** `mlx_lm.server` (or `steer_server.py` per architecture docs) on `http://localhost:8800`
- **Policy:** [STRICT_RULES.md](STRICT_RULES.md) requires real local inference — no mocks; completions via `http://localhost:8800/v1`

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

---

## Bottom line

This workspace is a local coding-agent cockpit: UI model cards are cosmetic/profile selectors; all four routes hit the same fused-gemma weights via MLX on port 8800, while the CLI/dashboard stitch orchestration, steering, MCP scaffolding, and DPO self-improvement into one Apple Silicon stack.
