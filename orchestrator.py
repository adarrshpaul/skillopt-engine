import os
import sys
import json
import subprocess
import argparse
from typing import List, Dict, Any
from urllib.request import Request, urlopen

# Default server URLs (compatible with local MLX / OpenAI-compatible endpoints)
PLANNER_URL = os.environ.get("PLANNER_URL", "http://localhost:8800/v1")
CODER_URL = os.environ.get("CODER_URL", "http://localhost:8800/v1")
DPO_LOG_PATH = os.environ.get("DPO_LOG_PATH", "/Users/adarrsh/workspace/dpo_logs.jsonl")

PLANNER_SYSTEM_PROMPT = """You are Gemma-4, a Master Software Architect. 
Given a high-level user goal, decompose it into a structured list of atomic code generation subtasks.
You MUST respond ONLY with a valid JSON array of objects, where each object has:
- "step_id": integer step number
- "description": clear specification of what code to write or edit
- "target_file": relative file path where code should be written
- "test_cmd": (optional) command to verify this step (e.g., "python -m py_compile main.py")

Example output format:
[
  {"step_id": 1, "description": "Write a math module with add and subtract functions.", "target_file": "math_utils.py", "test_cmd": "python -m py_compile math_utils.py"}
]
Do not include markdown code fences or explanatory text.
"""

CODER_SYSTEM_PROMPT = """You are Ornith, an Expert AI Coder.
Generate only valid, clean, self-contained Python code based on the task specification.
Do not include conversational filler or markdown fences. Output strictly raw executable code.
"""

def query_model(base_url: str, system_prompt: str, user_prompt: str, model_name: str = "AtomicChat/Ornith-9B-MLX-6bit") -> str:
    url = f"{base_url}/chat/completions"
    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "temperature": 0.2
    }
    req = Request(url, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"})
    try:
        with urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"[Orchestrator Error] Failed to contact model server at {base_url}: {e}")
        sys.exit(1)

def log_dpo_pair(prompt: str, rejected: str, chosen: str, error: str):
    entry = {
        "prompt": prompt,
        "rejected": rejected,
        "chosen": chosen,
        "error": error
    }
    with open(DPO_LOG_PATH, "a") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    print(f"  [DPO Flywheel] Logged failure/recovery pair to {DPO_LOG_PATH}")

def run_task_graph(goal: str):
    print(f"\n{'='*60}")
    print(f"🚀 Multi-Agent Orchestrator Starting Goal:")
    print(f"   \"{goal}\"")
    print(f"{'='*60}\n")

    # Step 1: Planner decomposes goal
    print("🧠 [1/2] Gemma-4 (Planner) generating task graph...")
    planner_response = query_model(PLANNER_URL, PLANNER_SYSTEM_PROMPT, f"User Goal: {goal}")
    
    # Clean up markdown if any leaked
    if planner_response.startswith("```"):
        planner_response = planner_response.strip("`").removeprefix("json").strip()

    try:
        task_graph: List[Dict[str, Any]] = json.loads(planner_response)
    except Exception as e:
        print(f"❌ Failed to parse task graph JSON from Planner: {e}")
        print(f"Raw Planner Output:\n{planner_response}")
        return

    print(f"✅ Planned {len(task_graph)} subtasks.")

    # Save task graph for IDE visualizer
    try:
        with open("task_graph.json", "w") as f:
            json.dump({"goal": goal, "tasks": task_graph}, f, indent=2)
    except Exception as e:
        print(f"Warning: Could not save task_graph.json: {e}")

    # Step 2: Coder executes tasks
    for task in task_graph:
        step_id = task.get("step_id")
        desc = task.get("description")
        target_file = task.get("target_file")
        test_cmd = task.get("test_cmd")

        print(f"\n💻 [2/2] Ornith (Coder) executing Step {step_id}: {desc}")
        code = query_model(CODER_URL, CODER_SYSTEM_PROMPT, f"Task: {desc}\nTarget File: {target_file}")
        
        # Clean up code fences
        if code.startswith("```"):
            lines = code.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            code = "\n".join(lines)

        # Write code to disk
        if target_file:
            os.makedirs(os.path.dirname(target_file) if os.path.dirname(target_file) else ".", exist_ok=True)
            with open(target_file, "w") as f:
                f.write(code)
            print(f"   Saved output to {target_file}")

        # Verification step
        if test_cmd:
            # Safely replace generic python with sys.executable
            exec_cmd = test_cmd.replace("python -m pytest", f"{sys.executable} -m unittest").replace("python ", f"{sys.executable} ")
            print(f"   Running verification: `{exec_cmd}`...")
            res = subprocess.run(exec_cmd, shell=True, capture_output=True, text=True)
            if res.returncode == 0:
                print(f"   ✅ Verification Passed!")
            else:
                print(f"   ❌ Verification Failed (code {res.returncode}): {res.stderr.strip()}")
                
                # Request Fix from Planner
                print("   🔄 Triggering Self-Correction via Gemma-4...")
                fix_prompt = f"The coder generated this code for '{desc}' which failed verification.\nError: {res.stderr}\nOriginal Code:\n{code}\nProvide the corrected code."
                fixed_code = query_model(PLANNER_URL, CODER_SYSTEM_PROMPT, fix_prompt)
                
                if fixed_code.startswith("```"):
                    lines = fixed_code.splitlines()
                    if lines[0].startswith("```"):
                        lines = lines[1:]
                    if lines and lines[-1].startswith("```"):
                        lines = lines[:-1]
                    fixed_code = "\n".join(lines)

                # Re-verify fixed code
                with open(target_file, "w") as f:
                    f.write(fixed_code)
                
                res_fix = subprocess.run(test_cmd, shell=True, capture_output=True, text=True)
                if res_fix.returncode == 0:
                    print(f"   🎉 Self-Correction Succeeded!")
                    # Log DPO pair: rejected=original_code, chosen=fixed_code
                    log_dpo_pair(desc, code, fixed_code, res.stderr.strip())
                else:
                    print(f"   ❌ Self-Correction failed again. Logging unrecovered failure.")
                    log_dpo_pair(desc, code, "", res.stderr.strip())

    print(f"\n{'='*60}")
    print(f"✨ Goal Execution Complete!")
    print(f"{'='*60}\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Multi-Agent Orchestrator")
    parser.add_argument("goal", type=str, nargs="?", default="Create a simple python module named greeting.py that has a greet(name) function and a test command.", help="High-level goal for the agents")
    args = parser.parse_args()

    run_task_graph(args.goal)
