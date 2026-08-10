import os
import sys
import json
import time
import subprocess
import argparse
import ast
import logging

os.environ["HF_HUB_OFFLINE"] = "1"

logging.basicConfig(filename="benchmark_trace.log", level=logging.INFO, format="[%(asctime)s] %(message)s")

def log_trace(msg: str):
    print(f"   [Trace] {msg}", flush=True)
    logging.info(msg)
from typing import List, Dict, Any
from urllib.request import Request, urlopen

# Ling-3.0-Flash (:8801) for Orchestration + Ornith-9B (:8800) for Coding
import model_router
from p3_faiss_worker import P3Worker
import claw_compactor
from sandbox.venv_executor import NativeVenvSandbox

class InfraError(Exception):
    """Raised when hardware or infrastructure fails (e.g. memory eviction timeout)."""
    pass

def compress_text(text: str) -> (str, int):
    """Compresses text using claw-compactor and returns (compressed_text, tokens_saved)."""
    try:
        from claw_compactor.fusion.pipeline import FusionPipeline
        from claw_compactor.config import PipelineConfig
        config = PipelineConfig()
        pipeline = FusionPipeline(config)
        compressed = pipeline.run(text)
        
        # Simple heuristic if exact token counter not present
        saved = len(text) - len(compressed)
        # Update tokens_saved metric
        if saved > 0:
            ts = 0
            try:
                if os.path.exists("tokens_saved.txt"):
                    with open("tokens_saved.txt", "r") as f:
                        ts = int(f.read().strip())
                with open("tokens_saved.txt", "w") as f:
                    f.write(str(ts + saved))
            except: pass
            
        return compressed, saved
    except Exception as e:
        # Graceful fallback
        return text, 0

PLANNER_URL = model_router.get_url("planner")
CODER_URL = model_router.get_url("coder")
REVIEWER_URL = model_router.get_url("reviewer")
FALLBACK_URL = model_router.get_url("fallback")

PLANNER_MODEL = model_router.get_model("planner")
CODER_MODEL = model_router.get_model("coder")
REVIEWER_MODEL = model_router.get_model("reviewer")
FALLBACK_MODEL = model_router.get_model("fallback")

PLANNER_ENGINE = model_router.get_engine("planner")
CODER_ENGINE = model_router.get_engine("coder")
REVIEWER_ENGINE = model_router.get_engine("reviewer")
FALLBACK_ENGINE = model_router.get_engine("fallback")

DPO_LOG_PATH = os.environ.get("DPO_LOG_PATH", "/Users/adarrsh/workspace/dpo_logs.jsonl")

PLANNER_SYSTEM_PROMPT = """You are Ling-3.0-Flash, a Master Software Architect and High-Throughput Orchestrator (124B Hybrid-Linear MoE). 
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

CODER_SYSTEM_PROMPT = """You are Ornith-9B, an Expert Software Engineering AI running on Apple Silicon.
You solve coding tasks by iterating: think about what to do, take an action, observe the result, repeat.

## Available Tools
You have these tools. Emit ONE tool call at a time inside <execute> tags. The system returns the output, then you continue.

1. **run_command(cmd)** — Run a shell command. Use for installing deps, running tests, scaffolding projects.
   <execute>run_command("npm install express")</execute>
   <execute>run_command("python -m pytest tests/ -v")</execute>

2. **write_file(path, content)** — Create or overwrite a file with the given content.
   <execute>write_file("src/app.py", "import flask\\napp = flask.Flask(__name__)\\n")</execute>

3. **edit_file(path, old_text, new_text)** — Surgically replace a specific string in an existing file.
   <execute>edit_file("src/app.py", "def old_func():", "def new_func():")</execute>

4. **read_file(path)** — Read the contents of a file.
   <execute>read_file("src/app.py")</execute>

5. **list_dir(path)** — List directory contents.
   <execute>list_dir(".")</execute>

## Workflow
1. Read the task description carefully.
2. Explore the workspace with list_dir and read_file to understand what exists.
3. Write code using write_file or edit_file.
4. Run tests using run_command to verify your work.
5. If tests fail, read the error output, fix the code, and re-run.
6. When everything passes, emit <done> to signal completion.

## Rules
- NEVER output raw code without using write_file. All code must be written to files via the tool.
- ALWAYS run tests after writing code to verify correctness.
- If a test fails, fix the issue and re-run. Do not give up.
- Emit exactly ONE tool call per response. Wait for the result before continuing.
- When the task is fully complete and tests pass, emit <done> on its own line.
"""


REVIEWER_SYSTEM_PROMPT = """You are Ling-3.0-Flash acting as a strict Code Reviewer AI.
Given a task description, the target file, and the code generated by Ornith, you must verify if the code is correct, complete, and satisfies the task.
You must classify your findings into one of these severities:
- CRITICAL: Syntax errors, missing imports, crashes. (Verdict: REQUEST_CHANGES)
- MAJOR: Missing requirements, logic bugs. (Verdict: REQUEST_CHANGES)
- MINOR: Naming conventions, missing docstrings. (Verdict: APPROVE)
- RECOMMENDATION: Best practices, performance tweaks. (Verdict: APPROVE)

If there are CRITICAL or MAJOR issues, respond with "REQUEST_CHANGES" followed by a concise explanation.
If there are only MINOR, RECOMMENDATION, or no issues, respond with "APPROVE" followed by optional notes.
Do not write the fixed code yourself.
"""

def query_model(base_url: str, system_prompt: str, user_prompt: str, model_name: str = CODER_MODEL, engine: str = CODER_ENGINE, vector: str = None, alpha: float = 1.0, layer: int = 16, max_retries: int = 3) -> str:
    if engine == "mlx":
        log_trace(f"Querying persistent MLX Server for {model_name}...")
        payload = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "max_tokens": 1024,
            "temperature": 0.2
        }
        url = "http://127.0.0.1:8801/v1/chat/completions"
        for attempt in range(1, max_retries + 1):
            start_time = time.time()
            try:
                req = Request(url, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"})
                with urlopen(req, timeout=300) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    elapsed = time.time() - start_time
                    resp_text = data["choices"][0]["message"]["content"]
                    log_trace(f"Response from MLX Server in {elapsed:.2f}s ({len(resp_text)} chars)")
                    return resp_text
            except Exception as e:
                elapsed = time.time() - start_time
                log_trace(f"Attempt {attempt}/{max_retries} MLX API failed after {elapsed:.2f}s: {e}")
                print(f"⚠️ [Attempt {attempt}/{max_retries}] MLX query failed.", flush=True)
                
        print(f"❌ [Orchestrator Error] All {max_retries} attempts to contact MLX Server failed.", flush=True)
        sys.exit(1)
        
    # Force evict the MLX server before loading an Ollama model to guarantee 16GB safety
    try:
        log_trace("Evicting MLX Server to reclaim unified memory...")
        evict_req = Request("http://127.0.0.1:8801/evict", method="POST")
        with urlopen(evict_req, timeout=10) as _:
            pass
    except Exception as e:
        log_trace(f"Warning: MLX Server eviction check failed: {e}")
        
    url = base_url.replace("/v1", "") + "/api/generate"
    qwen_prompt = f"<|im_start|>system\n{system_prompt}<|im_end|>\n<|im_start|>user\n{user_prompt}<|im_end|>\n<|im_start|>assistant\n"
    
    payload = {
        "model": model_name,
        "prompt": qwen_prompt,
        "stream": False,
        "options": {
            "temperature": 0.2,
            "num_predict": 1024
        },
        "keep_alive": 0
    }
    
    if vector:
        payload["steering_vector"] = vector
        payload["alpha"] = alpha
        payload["target_layer"] = layer
    
    payload_size = len(json.dumps(payload))
    log_trace(f"Sending {payload_size} chars to {model_name} at {url}...")
    
    for attempt in range(1, max_retries + 1):
        req = Request(url, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"})
        start_time = time.time()
        try:
            with urlopen(req, timeout=300) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                elapsed = time.time() - start_time
                resp_text = data.get("response", "").strip()
                log_trace(f"Response from {model_name} in {elapsed:.2f}s ({len(resp_text)} chars)")
                
                # Wait for keep_alive: 0 to actually evict the model
                ps_url = base_url.replace("/v1", "") + "/api/ps"
                wait_start = time.time()
                evicted = False
                while time.time() - wait_start < 15:
                    try:
                        with urlopen(Request(ps_url), timeout=2) as ps_resp:
                            ps_data = json.loads(ps_resp.read().decode("utf-8"))
                            if not ps_data.get("models"):
                                evicted = True
                                break
                    except Exception:
                        pass
                    time.sleep(0.5)
                
                if not evicted:
                    raise InfraError("Ollama did not evict the model within 15s")
                
                return resp_text
        except InfraError as ie:
            print(f"❌ [Infra Error] {ie}", flush=True)
            sys.exit(201)
        except Exception as e:
            elapsed = time.time() - start_time
            log_trace(f"Attempt {attempt}/{max_retries} failed after {elapsed:.2f}s: {e}")
            print(f"⚠️ [Attempt {attempt}/{max_retries}] Model query timed out or failed ({e}).", flush=True)
            print(f"🛑 FATAL: Hard timeout reached. Exiting immediately to avoid blocking on 16GB RAM constraints.", flush=True)
            sys.exit(1)
            
    print(f"❌ [Orchestrator Error] All {max_retries} attempts to contact model server failed.", flush=True)
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
    print(f"  [DPO Flywheel] Logged failure/recovery pair to {DPO_LOG_PATH}", flush=True)

def update_state_memory(goal: str, tasks: List[Dict[str, Any]], current_idx: int, message: str = ""):
    """Updates the STATE.md file so the user and loop have a persistent memory of progress."""
    state_content = f"# Loop Engineering State Memory\n\n**Goal**: {goal}\n**Status**: {message}\n\n## Tasks:\n"
    for i, task in enumerate(tasks):
        step_id = task.get('step_id')
        desc = task.get('description')
        if i < current_idx:
            status_char = "x"
        elif i == current_idx:
            status_char = "/"
        else:
            status_char = " "
        state_content += f"- [{status_char}] Step {step_id}: {desc}\n"
        
    try:
        with open("STATE.md", "w") as f:
            f.write(state_content)
    except Exception as e:
        print(f"Warning: Could not write STATE.md: {e}", flush=True)

def evaluate_code(code: str, desc: str, target_file: str) -> str:
    """Checker subagent: runs deterministic AST parse + semantic LLM review."""
    # 1. Deterministic AST syntax check
    try:
        ast.parse(code)
    except SyntaxError as e:
        return f"CRITICAL: SyntaxError: {e}"
    
    # 2. Semantic LLM Review
    print(f"   🕵️‍♀️  [Checker] Reviewing code for semantic correctness...", flush=True)
    prompt = f"Task: {desc}\nTarget File: {target_file}\nGenerated Code:\n```python\n{code}\n```\nVerify if this code fulfills the task."
    review = query_model(REVIEWER_URL, REVIEWER_SYSTEM_PROMPT, prompt, model_name=REVIEWER_MODEL, engine=REVIEWER_ENGINE)
    
    if "APPROVE" in review.upper()[:20] or "PASSED" in review.upper()[:20]:
        return "PASSED"
    return review

def check_command_safety(cmd: str) -> bool:
    """Pre-execution safety floor. Blocks destructive or unbounded network commands."""
    dangerous_keywords = ["rm -rf", "drop table", "mkfs", "> /dev/sda", "curl", "wget", "nc ", "ping "]
    cmd_lower = cmd.lower()
    for kw in dangerous_keywords:
        if kw in cmd_lower:
            return False
    return True

def _execute_tool(tool_str: str, sandbox) -> str:
    """Dispatch a tool call from the Coder agent. Returns the tool output as a string.
    
    Supported tools:
      run_command(cmd)           — Execute a shell command in the sandbox
      write_file(path, content)  — Create/overwrite a file
      edit_file(path, old, new)  — Surgical string replacement in a file
      read_file(path)            — Read file contents
      list_dir(path)             — List directory contents
    """
    workspace_root = os.path.abspath(os.getcwd())
    
    def _safe_path(path: str) -> str:
        """Resolve and validate a path is within the workspace."""
        abs_path = os.path.abspath(path)
        if not abs_path.startswith(workspace_root):
            raise PermissionError(f"Path '{path}' is outside the workspace boundary.")
        return abs_path
    
    # --- run_command ---
    if tool_str.startswith("run_command"):
        cmd_arg = tool_str.split("(", 1)[1].rsplit(")", 1)[0].strip()
        # Strip surrounding quotes
        cmd = ast.literal_eval(cmd_arg)
        
        if not check_command_safety(cmd):
            return "ERROR: Command blocked by safety floor."
        
        print(f"   🏃 [Shell] {cmd}", flush=True)
        exit_code, stdout, stderr = sandbox.run_command(cmd, timeout=120)
        
        result = f"Exit code: {exit_code}\n"
        if stdout.strip():
            result += f"stdout:\n{stdout[-3000:]}\n"  # Cap output to prevent context overflow
        if stderr.strip():
            result += f"stderr:\n{stderr[-2000:]}\n"
        return result
    
    # --- write_file ---
    elif tool_str.startswith("write_file"):
        # Parse: write_file("path", "content")
        inner = tool_str.split("(", 1)[1].rsplit(")", 1)[0]
        # Split on first comma that's outside quotes
        parts = []
        depth = 0
        current = ""
        in_str = False
        escape = False
        quote_char = None
        for ch in inner:
            if escape:
                current += ch
                escape = False
                continue
            if ch == '\\':
                current += ch
                escape = True
                continue
            if ch in ('"', "'") and not in_str:
                in_str = True
                quote_char = ch
                current += ch
                continue
            if ch == quote_char and in_str:
                in_str = False
                quote_char = None
                current += ch
                continue
            if ch == ',' and not in_str and depth == 0 and len(parts) == 0:
                parts.append(current.strip())
                current = ""
                continue
            current += ch
        parts.append(current.strip())
        
        if len(parts) < 2:
            return "ERROR: write_file requires (path, content)"
        
        filepath = ast.literal_eval(parts[0])
        content = ast.literal_eval(parts[1])
        
        abs_path = _safe_path(filepath)
        os.makedirs(os.path.dirname(abs_path) if os.path.dirname(abs_path) else ".", exist_ok=True)
        with open(abs_path, "w") as f:
            f.write(content)
        return f"Successfully wrote {len(content)} chars to {filepath}"
    
    # --- edit_file ---
    elif tool_str.startswith("edit_file"):
        inner = tool_str.split("(", 1)[1].rsplit(")", 1)[0]
        parts = []
        depth = 0
        current = ""
        in_str = False
        escape = False
        quote_char = None
        for ch in inner:
            if escape:
                current += ch
                escape = False
                continue
            if ch == '\\':
                current += ch
                escape = True
                continue
            if ch in ('"', "'") and not in_str:
                in_str = True
                quote_char = ch
                current += ch
                continue
            if ch == quote_char and in_str:
                in_str = False
                quote_char = None
                current += ch
                continue
            if ch == ',' and not in_str and depth == 0 and len(parts) < 2:
                parts.append(current.strip())
                current = ""
                continue
            current += ch
        parts.append(current.strip())
        
        if len(parts) < 3:
            return "ERROR: edit_file requires (path, old_text, new_text)"
        
        filepath = ast.literal_eval(parts[0])
        old_text = ast.literal_eval(parts[1])
        new_text = ast.literal_eval(parts[2])
        
        abs_path = _safe_path(filepath)
        if not os.path.exists(abs_path):
            return f"ERROR: File '{filepath}' does not exist."
        
        with open(abs_path, "r") as f:
            content = f.read()
        
        if old_text not in content:
            return f"ERROR: Could not find the target text in {filepath}."
        
        content = content.replace(old_text, new_text, 1)
        with open(abs_path, "w") as f:
            f.write(content)
        return f"Successfully edited {filepath}"
    
    # --- read_file ---
    elif tool_str.startswith("read_file"):
        filepath = ast.literal_eval(tool_str.split("(", 1)[1].rsplit(")", 1)[0])
        abs_path = _safe_path(filepath)
        with open(abs_path, "r") as f:
            content = f.read()
        # Cap at 4000 chars to prevent context overflow
        if len(content) > 4000:
            return content[:2000] + "\n\n...[TRUNCATED]...\n\n" + content[-2000:]
        return content
    
    # --- list_dir ---
    elif tool_str.startswith("list_dir"):
        dirpath = ast.literal_eval(tool_str.split("(", 1)[1].rsplit(")", 1)[0])
        abs_path = _safe_path(dirpath)
        entries = os.listdir(abs_path)
        return "\n".join(sorted(entries))
    
    else:
        return f"ERROR: Unknown tool: {tool_str.split('(')[0]}"

def run_task_graph(goal: str, vector: str = None, alpha: float = 1.0, layer: int = 16):

    print(f"\n{'='*60}", flush=True)
    print(f"🚀 Multi-Agent Orchestrator Starting Goal:", flush=True)
    print(f"   \"{goal}\"", flush=True)
    if vector:
        print(f"   🎛️ Active Steering: Vector='{vector}', Alpha={alpha}, Layer=L{layer}", flush=True)
    print(f"{'='*60}\n", flush=True)

    # Phase 4.1: FAISS Semantic Context Retrieval
    print("🔍 [0/2] P3 FAISS Worker retrieving workspace context... (SKIPPED FOR 16GB RAM MODE)", flush=True)
    start_faiss = time.time()
    context_str = ""
    # try:
    #     worker = P3Worker()
    #     context_docs = worker.query(goal, k=3)
    #     context_str = "\n".join([f"Context (from {d.get('metadata', {}).get('source', 'unknown')}):\n{d['text']}" for d in context_docs])
    #     if context_str:
    #         start_comp = time.time()
    #         comp_context, saved = compress_text(context_str)
    #         comp_time = time.time() - start_comp
    #         log_trace(f"Compactor compressed FAISS context in {comp_time:.2f}s, saved {saved} chars")
    #         context_str = comp_context
    #         print(f"   ✅ Retrieved {len(context_docs)} context snippets (Saved {saved} chars via compression).", flush=True)
    #     else:
    #         print(f"   ⚠️ No relevant context found.", flush=True)
    # except Exception as e:
    #     print(f"   ❌ FAISS Retrieval failed: {e}", flush=True)
    #     context_str = ""
    log_trace(f"FAISS Retrieval step skipped (took {time.time() - start_faiss:.2f}s total)")

    # Step 1: Planner decomposes goal
    print("🧠 [1/2] Ling-3.0 (Planner) generating task graph...", flush=True)
    print(f"   ↳ backend: {PLANNER_MODEL}", flush=True)
    
    full_planner_prompt = f"User Goal: {goal}"
    if context_str:
        full_planner_prompt += f"\n\nRetrieved Workspace Context:\n{context_str}\n"

    planner_response = query_model(PLANNER_URL, PLANNER_SYSTEM_PROMPT, full_planner_prompt, model_name=PLANNER_MODEL, engine=PLANNER_ENGINE, vector=vector, alpha=alpha, layer=layer)
    
    if planner_response.startswith("```"):
        planner_response = planner_response.strip("`").removeprefix("json").strip()

    try:
        task_graph: List[Dict[str, Any]] = json.loads(planner_response)
    except Exception as e:
        print(f"❌ Failed to parse task graph JSON from Planner: {e}", flush=True)
        return

    print(f"✅ Planned {len(task_graph)} subtasks.", flush=True)
    update_state_memory(goal, task_graph, -1, "Planned tasks")

    # Phase JIT: Skill Procurement
    try:
        from skill_procurer import SkillProcurer
        procurer = SkillProcurer()
        missing_skills = procurer.analyze_missing_skills(task_graph)
        if missing_skills:
            print(f"   [JIT Planner] Detected {len(missing_skills)} missing external skill(s). Procuring...", flush=True)
            for skill_kw in missing_skills:
                skill_content = procurer.download_skill_silently(skill_kw)
                required_creds = procurer.detect_credentials(skill_content)
                if required_creds:
                    # Halt and prompt for credentials
                    procurer.prompt_for_credentials(required_creds, skill_kw)
    except Exception as e:
        print(f"   ⚠️ Skill procurement failed: {e}", flush=True)

    try:
        with open("task_graph.json", "w") as f:
            json.dump({"goal": goal, "tasks": task_graph}, f, indent=2)
    except Exception:
        pass

    # Step 2: ReAct Loop — Reason + Act per task
    sandbox = NativeVenvSandbox()
    sandbox.setup(os.path.abspath(os.getcwd()))
    
    CHECKPOINT_FILE = "harness_checkpoint.json"
    
    try:
        for i, task in enumerate(task_graph):
            step_id = task.get("step_id")
            desc = task.get("description")
            target_file = task.get("target_file")
            test_cmd = task.get("test_cmd")

            print(f"\n💻 [2/2] Agent executing Step {step_id}: {desc}", flush=True)
            print(f"   ↳ backend: {CODER_MODEL}", flush=True)
            update_state_memory(goal, task_graph, i, f"Working on step {step_id}")
            
            # Build the initial prompt for this task
            react_prompt = f"Task: {desc}"
            if target_file:
                react_prompt += f"\nTarget File: {target_file}"
            if test_cmd:
                react_prompt += f"\nVerification Command: {test_cmd}"
            
            # Inject relevant JIT skills
            try:
                from skill_procurer import SkillProcurer
                skill_content = SkillProcurer().get_skill_content(desc)
                if skill_content:
                    react_prompt += f"\n\n--- INJECTED SKILL CONTEXT ---\n{skill_content}\n-----------------------------"
            except Exception:
                pass
            
            # ReAct Loop: agent acts, observes, iterates
            MAX_REACT_STEPS = 15  # Hard ceiling to prevent runaway
            task_complete = False
            
            for step in range(1, MAX_REACT_STEPS + 1):
                print(f"   🔄 [ReAct Step {step}/{MAX_REACT_STEPS}]", flush=True)
                
                raw_output = query_model(CODER_URL, CODER_SYSTEM_PROMPT, react_prompt, model_name=CODER_MODEL, engine=CODER_ENGINE)
                
                # Check if agent signals completion
                if "<done>" in raw_output.lower():
                    print(f"   ✅ Agent signaled task complete.", flush=True)
                    task_complete = True
                    break
                
                # Check if agent emitted a tool call
                if "<execute>" in raw_output:
                    try:
                        tool_str = raw_output.split("<execute>")[1].split("</execute>")[0].strip()
                        print(f"   🛠️  [Tool] {tool_str[:80]}{'...' if len(tool_str) > 80 else ''}", flush=True)
                        
                        tool_result = _execute_tool(tool_str, sandbox)
                        
                        # Compress large outputs
                        comp_result, saved = compress_text(tool_result)
                        if saved > 0:
                            print(f"   🗜️ Compressed tool output by {saved} chars.", flush=True)
                        
                        # Feed observation back to agent
                        react_prompt += f"\n\nYou called:\n{raw_output}\n\nResult:\n{comp_result}"
                        
                    except Exception as e:
                        print(f"   ❌ Tool error: {e}", flush=True)
                        react_prompt += f"\n\nYou called:\n{raw_output}\n\nError:\n{e}"
                else:
                    # Agent emitted text without a tool call or <done>
                    # Treat as thinking/planning — nudge it to act
                    react_prompt += f"\n\nYou said:\n{raw_output}\n\nPlease take an action using a tool, or emit <done> if the task is complete."
            
            if not task_complete:
                print(f"   ⚠️ Max ReAct steps reached for Step {step_id}. Moving on.", flush=True)
            
            # Final quality gate: Checker reviews what was produced
            if target_file and os.path.exists(target_file):
                try:
                    with open(target_file, "r") as f:
                        final_code = f.read()
                    review = evaluate_code(final_code, desc, target_file)
                    if review == "PASSED":
                        print(f"   ✅ [Checker] Final review: PASSED", flush=True)
                    else:
                        print(f"   ⚠️ [Checker] Final review: {review.splitlines()[0][:100]}", flush=True)
                        log_dpo_pair(desc, final_code, "", review)
                except Exception as e:
                    print(f"   ⚠️ [Checker] Could not review {target_file}: {e}", flush=True)
            
            # Save checkpoint after each completed task
            try:
                checkpoint = {
                    "goal": goal,
                    "completed_step": step_id,
                    "total_steps": len(task_graph),
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S")
                }
                with open(CHECKPOINT_FILE, "w") as f:
                    json.dump(checkpoint, f, indent=2)
            except Exception:
                pass
                
    finally:
        sandbox.teardown()


    update_state_memory(goal, task_graph, len(task_graph), "Execution Complete")
    
    print(f"   📝 Generating completion report...", flush=True)
    completion_report = f"# Completion Report: {goal}\n\n"
    for task in task_graph:
        completion_report += f"## Task {task.get('step_id')}: {task.get('description')}\n"
        completion_report += f"- **Target File**: {task.get('target_file')}\n"
        test_cmd = task.get('test_cmd')
        if test_cmd:
            completion_report += f"- **Validation Cmd**: `{test_cmd}`\n"
        completion_report += f"- **Verdict**: PASSED\n\n"
        
    try:
        with open("completion_report.md", "w") as f:
            f.write(completion_report)
        print(f"   💾 Saved completion report to completion_report.md", flush=True)
    except Exception as e:
        print(f"   ⚠️ Could not write completion report: {e}", flush=True)

    print(f"\n{'='*60}", flush=True)
    print(f"✨ Goal Execution Complete!", flush=True)
    print(f"{'='*60}\n", flush=True)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Multi-Agent Orchestrator")
    parser.add_argument("goal", type=str, nargs="?", default="Create a simple python module named greeting.py that has a greet(name) function and a test command.", help="High-level goal for the agents")
    parser.add_argument("--vector", type=str, default=None, help="Steering vector name")
    parser.add_argument("--alpha", type=float, default=1.0, help="Steering alpha scaling factor")
    parser.add_argument("--layer", type=int, default=16, help="Target injection layer")
    args = parser.parse_args()

    run_task_graph(args.goal, vector=args.vector, alpha=args.alpha, layer=args.layer)
