#!/Users/adarrsh/workspace/auto-dev-env/bin/python
"""
Headless Autonomous Developer Daemon — Project Ornith Edition
Continuously monitors .tasks/queue.md and spawns agents to execute them.

Supports two modes:
  --gemini    : Uses Antigravity SDK + Gemini API (requires GEMINI_API_KEY)
  --ornith    : Uses the local 5-layer Ornith stack (zero cost, no API key needed)
"""

import asyncio
import argparse
import json
import os
import re
import time
import subprocess
import urllib.request
import urllib.error
from pathlib import Path

# Import our custom components
try:
    from harness import ExecutionHarness
except ImportError:
    print("FATAL: harness.py not found in workspace.")
    exit(1)

try:
    from context_engine import ContextEngine
except ImportError:
    print("WARNING: context_engine.py not found. Context layer disabled.")
    ContextEngine = None

try:
    from prompt_optimizer import PromptOptimizer
except ImportError:
    print("WARNING: prompt_optimizer.py not found. Prompt optimization disabled.")
    PromptOptimizer = None


WORKSPACE_DIR = Path(os.environ.get("WORKSPACE_DIR", "/Users/adarrsh/workspace"))
QUEUE_FILE = WORKSPACE_DIR / ".tasks" / "queue.md"
DONE_DIR = WORKSPACE_DIR / ".tasks" / "done"

OLLAMA_URL = "http://localhost:11434"
ORNITH_MODEL = os.environ.get("ORNITH_MODEL", "gemma4:12b")


# ─── Task Queue ───────────────────────────────────────────────────

def extract_next_task() -> dict | None:
    """Reads queue.md and pops the first pending task."""
    if not QUEUE_FILE.exists():
        return None

    content = QUEUE_FILE.read_text(encoding="utf-8")
    task_pattern = re.compile(r"(### TASK-\d+:.*?)(?=### TASK-\d+:|---|$)", re.DOTALL | re.MULTILINE)
    match = task_pattern.search(content)

    if not match:
        return None

    task_block = match.group(1).strip()

    if "(human / agent name)" in task_block and "What needs to be done." in task_block:
        matches = task_pattern.findall(content)
        if len(matches) <= 1:
            return None
        task_block = matches[1].strip()

    new_content = content.replace(task_block, "", 1)
    QUEUE_FILE.write_text(new_content, encoding="utf-8")
    return {"raw": task_block}


# ─── Ornith Mode: 5-Layer Local Inference ─────────────────────────

def query_ollama(prompt: str, model: str = None, system: str = "") -> str:
    """Send a prompt to the local MLX inference script."""
    import subprocess
    
    # Format for Gemma 2 Instruction tuned models
    full_prompt = f"<start_of_turn>user\n{system}\n{prompt}<end_of_turn>\n<start_of_turn>model\n"
    
    try:
        result = subprocess.run(
            ["/Users/adarrsh/workspace/ml-env/bin/python", "/Users/adarrsh/workspace/mlx_infer.py"],
            input=full_prompt, text=True, capture_output=True, check=True
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        return f"[MLX Error: {e.stderr}]"


def ornith_5layer_pipeline(task_text: str, harness: ExecutionHarness) -> str:
    """
    Execute a task through the full 5-layer Ornith stack:
      Layer 1: Context Engine (RAG retrieval)
      Layer 2: Prompt Optimizer (system prompt + few-shot + CoT)
      Layer 3: Fine-tuned model inference via Ollama
      Layer 4: (Future) Activation steering
      Layer 5: Execution harness with self-heal
    """
    print("[Ornith] ── Layer 1: Context Engine ──")
    context = ""
    if ContextEngine is not None:
        try:
            engine = ContextEngine(str(WORKSPACE_DIR))
            engine.index_workspace()
            engine.index_trajectories()
            context = engine.build_context(task_text, token_budget=2048)
            print(f"[Ornith]   Retrieved {len(context)} chars of context")
        except Exception as e:
            print(f"[Ornith]   Context engine failed: {e}")

    print("[Ornith] ── Layer 2: Prompt Optimizer ──")
    system_prompt = ""
    optimized_prompt = task_text
    if PromptOptimizer is not None:
        try:
            optimizer = PromptOptimizer()
            task_type = optimizer.classify_task(task_text)
            system_prompt = optimizer.get_system_prompt(task_type)
            optimized_prompt = optimizer.optimize(task_text, context=context)
            print(f"[Ornith]   Task classified as: {task_type}")
            print(f"[Ornith]   Optimized prompt: {len(optimized_prompt)} chars")
        except Exception as e:
            print(f"[Ornith]   Prompt optimizer failed: {e}")
            optimized_prompt = f"{context}\n\n{task_text}" if context else task_text

    print("[Ornith] ── Layer 3: Local Model Inference ──")
    response = query_ollama(optimized_prompt, system=system_prompt)
    print(f"[Ornith]   Model response: {len(response)} chars")

    print("[Ornith] ── Layer 4: Activation Steering ── (pending steer_server)")

    print("[Ornith] ── Layer 5: Execution Harness ──")
    # Parse the model's response for shell commands and execute them
    code_blocks = re.findall(r"```(?:bash|sh|shell)?\n(.*?)```", response, re.DOTALL)
    if code_blocks:
        for i, cmd_block in enumerate(code_blocks):
            for cmd in cmd_block.strip().split("\n"):
                cmd = cmd.strip()
                if cmd and not cmd.startswith("#"):
                    print(f"[Ornith]   Executing: {cmd}")
                    result = harness.execute_with_self_heal(cmd, max_retries=2)
                    # Feed the result back to the model for the next iteration
                    response += f"\n\n[Harness Output for `{cmd}`]:\n{result}"

    # Log the full interaction for GRPO training
    harness.log_agent_action(
        action_type="ornith_5layer",
        input_data=task_text,
        output_data=response,
        reward=0.0  # Will be scored by diff_engine later
    )

    return response


# ─── Gemini Mode: Antigravity SDK ─────────────────────────────────

async def execute_task_gemini(task_text: str):
    """Execute a task using the Antigravity SDK (requires GEMINI_API_KEY)."""
    from google.antigravity import Agent, LocalAgentConfig, types

    task_id_match = re.search(r"TASK-\d+", task_text)
    task_id = task_id_match.group(0) if task_id_match else f"TASK-UNKNOWN-{int(time.time())}"
    harness = ExecutionHarness(task_id, str(WORKSPACE_DIR))

    MCP_VENV = "/Users/adarrsh/siemens-ix-mcp/.venv/bin/python"
    mcp_servers = [
        types.McpStdioServer(
            name="siemens-ix",
            command=MCP_VENV,
            args=["-m", "siemens_ix_mcp"],
        )
    ]

    agent_config = LocalAgentConfig(
        mcp_servers=mcp_servers,
        tools=[harness.execute_command],
        capabilities=types.CapabilitiesConfig(enable_subagents=True),
        system_instruction=(
            "You are an autonomous developer agent. Solve the task completely. "
            "Do not ask for user feedback. Use execute_command for shell commands."
        )
    )

    async with Agent(agent_config) as agent:
        prompt = f"Task:\n\n{task_text}\n\nExecute this task now."
        try:
            response = await agent.chat(prompt)
            text = await response.text()
            print(f"[Gemini] Agent finished. Preview: {text[:500]}...")
        except Exception as e:
            print(f"[Gemini] Agent failed: {e}")


# ─── Ornith Mode Task Execution ───────────────────────────────────

def execute_task_ornith(task_text: str):
    """Execute a task using the local 5-layer Ornith stack (no API key needed)."""
    print(f"\n[Ornith] ═══ Processing Task ═══")
    print(f"{'-'*50}\n{task_text}\n{'-'*50}")

    task_id_match = re.search(r"TASK-\d+", task_text)
    task_id = task_id_match.group(0) if task_id_match else f"TASK-UNKNOWN-{int(time.time())}"
    harness = ExecutionHarness(task_id, str(WORKSPACE_DIR))

    response = ornith_5layer_pipeline(task_text, harness)

    # Save result
    DONE_DIR.mkdir(parents=True, exist_ok=True)
    done_file = DONE_DIR / f"{task_id}.md"
    done_file.write_text(
        f"# {task_id} — Completed\n\n"
        f"## Task\n{task_text}\n\n"
        f"## Response\n{response}\n",
        encoding="utf-8"
    )
    print(f"[Ornith] ═══ Task saved to {done_file} ═══\n")


# ─── Main Loop ────────────────────────────────────────────────────

async def main():
    parser = argparse.ArgumentParser(description="Auto-Dev Daemon — Project Ornith")
    parser.add_argument("--ornith", action="store_true", help="Use local 5-layer Ornith stack (no API key)")
    parser.add_argument("--colab", action="store_true", help="Automate ML training in Google Colab via Chrome CDP")
    parser.add_argument("--gemini", action="store_true", help="Use Antigravity SDK + Gemini API")
    parser.add_argument("--model", type=str, default=None, help="Override Ollama model name")
    args = parser.parse_args()

    global ORNITH_MODEL
    if args.model:
        ORNITH_MODEL = args.model

    mode = "ornith" if args.ornith else ("gemini" if args.gemini else "ornith")
    print(f"🚀 Auto-Dev Daemon started in [{mode.upper()}] mode.")
    print(f"   Monitoring: {QUEUE_FILE}")
    if mode == "ornith":
        print(f"   Model: {ORNITH_MODEL}")
        print(f"   Layers: Context + Prompt Optimizer + Local Model + Steering + Harness")
    DONE_DIR.mkdir(parents=True, exist_ok=True)

    while True:
        task = extract_next_task()
        if task:
            if mode == "gemini":
                await execute_task_gemini(task["raw"])
            else:
                execute_task_ornith(task["raw"])
        else:
            await asyncio.sleep(10)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nShutting down Auto-Dev Daemon.")
