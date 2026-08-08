# STRICT WORKSPACE POLICY: NO SIMULATIONS OR MOCKS EVER

> **Enforcement Scope:** All AI agents, harnesses, orchestrators, code generators, server APIs, and UI responses operating in this workspace. This is a production distribution project.

## 🚨 MANDATORY DIRECTIVES

1. **ABSULUTE ZERO MOCKING POLICY**:
   - **NO MOCK / DUMMY TEXT IN APIS OR UI**: Server endpoints (e.g. `/api/chat`, `/api/generate`) MUST NEVER return mock strings like `"This is a mocked LLM response..."` or canned fallback text under any circumstances.
   - If a model server is offline or unreachable, return a real HTTP 503 error stating the model endpoint on `:8800`/`:8801` is offline. Do NOT mask errors with fake mock responses.

2. **NO MOCK OR DUMMY CODE**:
   - Every synthesized code snippet must be 100% functional, production-ready, and executable.
   - Never output hardcoded boilerplate algorithms (e.g. `hash(items)`, dummy loops) to substitute for real logic.

3. **DETERMINISTIC COMPILATION & TESTING**:
   - Every synthesized module must pass Python `ast.parse()` compilation.
   - Every synthesized module must be written to disk at `/Users/adarrsh/workspace` and executed via `subprocess.run()` or `unittest` to verify zero runtime errors.

4. **REAL LOCAL MODEL INFERENCE**:
   - Connect directly to the local MLX / PyTorch model servers running on `http://localhost:8801/v1` (Planner/Ling) and `http://localhost:8800/v1` (Coder/Ornith) for real inference completions.
   - If the local inference server is loading heavy weights, wait for the actual output without substituting fake responses.

5. **VERIFIABLE ARTIFACTS**:
   - All generated code files (`.py`, `.json`, `.sh`) must exist physically on the file system and be executable directly from terminal.
