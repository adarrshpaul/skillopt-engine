# SkillOpt Workspace Conventions (PROJECT.md)

> This file is automatically loaded into the Agent Harness on every turn as Tier 1 Persistent Memory.

## 🛠️ Build & Test Commands
- **Compile Check:** `python3 -m py_compile <filename>.py`
- **Run Unit Tests:** `python3 test_suite.py` or `pytest`
- **Run Orchestrator:** `python3 orchestrator.py --goal "<goal>"`
- **Start UI:** `python3 chat_ui.py` (Side-by-side Artifact UI)

## 📋 Code Standards
- **Python Version:** 3.10+ compatible (Type hints, clean imports).
- **Execution Model:** Fully offline Apple Silicon MLX GPU acceleration or local HTTP endpoint.
- **Loop Engineering:** Always use the Maker-Checker pattern. Code must pass deterministic AST parsing before execution.
- **Safety Policy:** Non-destructive operations only. Sandboxed shell execution by default.

## 🚀 Future Enhancements (Ideas from Atomic-Chat Analysis)
- **Plugin Architecture for Engines:** Implement a Strategy Pattern to decouple inference backends. Currently, `orchestrator.py` hardcodes `if engine == "mlx": ... elif engine == "ollama": ...`. We should abstract this using distinct backend extension plugins (e.g., `extensions/llamacpp-extension` and `extensions/mlx-extension`).
- **Cross-Platform Bundling (Tauri):** Wrap the Python orchestrator in a lightweight Tauri frontend instead of running terminal scripts like `python scripts/run_swe_bench.py`. This is the definitive way to package and ship the SkillOpt Engine to end users as a standalone desktop app.
- **Automated QA Harness:** Build a headless test runner similar to Atomic-Chat's `autoqa/` directory that spins up instances to record test interactions. This will be invaluable for scaling `run_swe_bench.py` to hundreds of automated tests.
