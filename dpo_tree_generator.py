import os
import sys
import json
import subprocess
import argparse
from typing import List, Dict, Any
from urllib.request import Request, urlopen

MODEL_URL = os.environ.get("CODER_URL", "http://localhost:8800/v1")
MODEL_NAME = os.environ.get("CODER_MODEL", "AtomicChat/Ornith-9B-MLX-6bit")
DATASET_PATH = os.environ.get("DPO_DATASET_PATH", "/Users/adarrsh/workspace/dpo_graph_dataset.jsonl")

CODER_SYSTEM_PROMPT = """You are Ornith, an Expert AI Coder.
Generate clean, valid Python code to solve the specified task.
Outputs must contain ONLY valid python code, with no preamble, no markdown, and no code blocks.
"""

def query_candidate(prompt: str, temperature: float) -> str:
    url = f"{MODEL_URL}/chat/completions"
    payload = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": CODER_SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ],
        "temperature": temperature
    }
    req = Request(url, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"})
    try:
        with urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            msg = data["choices"][0]["message"]
            code = (msg.get("content") or "").strip()
            if code.startswith("```"):
                lines = code.splitlines()
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].startswith("```"):
                    lines = lines[:-1]
                code = "\n".join(lines)
            return code
    except Exception as e:
        print(f"[Tree Gen Error] Model request failed: {e}")
        return ""

def evaluate_code(code: str, target_file: str = "temp_candidate.py") -> tuple[bool, str]:
    """Executes the candidate code in a sandbox process to determine ground truth validity."""
    with open(target_file, "w") as f:
        f.write(code)

    # Step 1: Syntax / Compilation Check
    res = subprocess.run([sys.executable, "-m", "py_compile", target_file], capture_output=True, text=True)
    if res.returncode != 0:
        return False, f"Syntax/Compile Error: {res.stderr.strip()}"

    # Step 2: Doctest / Execution Check if file is executable
    res_exec = subprocess.run([sys.executable, target_file], capture_output=True, text=True, timeout=5)
    if res_exec.returncode != 0:
        return False, f"Runtime Error: {res_exec.stderr.strip()}"

    return True, "Passed Execution Verification"

def explore_and_generate_dpo_pairs(task_prompt: str, num_branches: int = 4):
    print(f"\n{'='*60}")
    print(f"🌳 Graph-Based DPO Decision Tree Generator")
    print(f"   Task: \"{task_prompt}\"")
    print(f"   Exploring {num_branches} execution branches...")
    print(f"{'='*60}\n")

    temperatures = [0.1, 0.4, 0.7, 0.9][:num_branches]
    success_branches = []
    failure_branches = []

    for i, temp in enumerate(temperatures):
        print(f"  🌿 Branch {i+1}/{num_branches} (Temperature={temp})...")
        candidate_code = query_candidate(task_prompt, temperature=temp)
        
        if not candidate_code:
            continue

        temp_file = f"branch_{i+1}.py"
        passed, log_msg = evaluate_code(candidate_code, temp_file)

        # Cleanup temp file
        if os.path.exists(temp_file):
            os.remove(temp_file)

        if passed:
            print(f"     ✅ [SUCCESS Node] Valid code path found.")
            success_branches.append(candidate_code)
        else:
            print(f"     ❌ [FAILURE Node] {log_msg}")
            failure_branches.append((candidate_code, log_msg))

    print(f"\n📊 Traversal Complete: {len(success_branches)} Successes, {len(failure_branches)} Failures.")

    # Pair Success vs Failure nodes for DPO dataset
    pairs_generated = 0
    if success_branches and failure_branches:
        with open(DATASET_PATH, "a") as f:
            for chosen in success_branches:
                for rejected, error_msg in failure_branches:
                    record = {
                        "prompt": task_prompt,
                        "chosen": chosen,
                        "rejected": rejected,
                        "execution_error": error_msg
                    }
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")
                    pairs_generated += 1
        print(f"🎉 Successfully logged {pairs_generated} verified DPO preference pairs to {DATASET_PATH}")
    elif not success_branches:
        print("⚠️ No successful branches found. Consider relaxing verification requirements.")
    else:
        print("ℹ️ All branches succeeded! No failure pairs generated for this prompt.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Graph-Based Execution Tree DPO Generator")
    parser.add_argument("task", type=str, nargs="?", default="Write a python function `is_palindrome(s: str) -> bool` with doctests.", help="Task specification")
    parser.add_argument("--branches", type=int, default=4, help="Number of exploration branches")
    args = parser.parse_args()

    explore_and_generate_dpo_pairs(args.task, args.branches)
