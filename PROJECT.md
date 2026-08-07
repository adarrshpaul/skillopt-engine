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
