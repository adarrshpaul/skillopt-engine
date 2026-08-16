import os
import sys
from dotenv import load_dotenv
load_dotenv()
import json
import time
import subprocess
import argparse
import ast
import logging
from pathlib import Path

os.environ["HF_HUB_OFFLINE"] = "1"

logging.basicConfig(filename="benchmark_trace.log", level=logging.INFO, format="[%(asctime)s] %(message)s")

def log_trace(msg: str):
    print(f"   [Trace] {msg}", flush=True)
    logging.info(msg)
from typing import List, Dict, Any
import random
import urllib.error
from urllib.request import Request, urlopen

# Heterogeneous Multi-Agent Architecture (Planner + Coder + Reviewer + MLX Fallback)
import model_router
from p3_faiss_worker import P3Worker
import claw_compactor
from sandbox.venv_executor import NativeVenvSandbox

# Core Harness Framework (DeepSeek & Claude Code Harness Synthesis)
from core.session_ledger import JSONLSessionLedger, SessionEvent
from core.safety_gate import evaluate_tool_call, Decision
from core.tool_pipeline import ToolPipeline, ToolCall, ToolResult, parse_tool_calls_from_text
from core.task_ledger import MarkdownTaskLedger, TaskSpec
from core.compaction import CompactionGovernor, save_wip_state, restore_wip_state, clear_wip_state
from core.output_extractor import extract_json_array, extract_json_object
from core.lsp_client import (
    handle_find_definition,
    handle_find_references,
    handle_document_symbols,
    handle_hover,
    get_symbol_index
)

class InfraError(Exception):
    """Raised when hardware or infrastructure fails (e.g. memory eviction timeout)."""
    pass

def compress_text(text: str) -> tuple[str, int]:
    """Compresses text via ClawCompactor. Returns (compressed_text, chars_saved)."""
    try:
        compressed, saved = claw_compactor.compress(text)
        if saved > 0:
            try:
                with open("tokens_saved.txt", "r") as f:
                    ts = int(f.read().strip())
            except:
                ts = 0
            try:
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

PLANNER_SYSTEM_PROMPT = """You are a Master Software Architect and High-Throughput Orchestrator. 
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

CODER_SYSTEM_PROMPT = """You are an Expert Software Engineering AI.
You solve coding tasks by iterating: think about what to do, take an action, observe the result, repeat.

## Available Tools
You have these tools. Emit ONE tool call at a time inside <execute> tags. The system returns the output, then you continue.

1. **find_definition(symbol, file_path=None)** — Jump directly to class, function, or method definition.
   <execute>find_definition("CompactionGovernor")</execute>

2. **find_references(symbol, file_path=None)** — Find all callers and call sites of a symbol across the codebase.
   <execute>find_references("save_wip_state")</execute>

3. **document_symbols(path)** — Get the full outline (classes, methods, functions) of a file.
   <execute>document_symbols("core/compaction.py")</execute>

4. **hover(symbol, file_path=None)** — View type signature, docstring, and line location of a symbol.
   <execute>hover("estimate_tokens")</execute>

5. **run_command(cmd, is_daemon=False)** — Run a shell command. Set is_daemon=True for long-running servers.
   <execute>run_command("pytest tests/ -v")</execute>

6. **manage_task(action, task_id)** — Manage background tasks. Action can be "status" or "kill".
   <execute>manage_task("status", "task_1")</execute>

7. **write_file(path, content)** — Create or overwrite a file with the given content.
   <execute>write_file("src/app.py", "import flask\\napp = flask.Flask(__name__)\\n")</execute>

8. **replace_file_content(path, start_line, end_line, replacement_content)** — Surgically replace lines in an existing file. Lines are 1-indexed.
   <execute>replace_file_content("src/app.py", 10, 15, "def new_func():\\n    pass\\n")</execute>

9. **read_file(path)** — Read file content (fallback for text/yaml/json/md configs).
   <execute>read_file("config.yaml")</execute>

10. **list_dir(path)** — List directory contents.
   <execute>list_dir(".")</execute>

11. **update_plan(new_tasks)** — Replace all remaining upcoming tasks with a new list of tasks. Each task must have {"step_id": int, "description": "...", "target_file": "..."}.
   <execute>update_plan([{"step_id": 3, "description": "Refactor router", "target_file": "router.py"}])</execute>

## Workflow
1. Use `find_definition`, `find_references`, and `document_symbols` to inspect code symbols semantically.
2. Write code using write_file or replace_file_content.
3. Run tests using run_command to verify your work.
4. If tests fail, read the error output, fix the code, and re-run.
5. When everything passes, emit <done> to signal completion.

## Rules
- ALWAYS prefer find_definition and find_references over reading entire files.
- NEVER output raw code without using write_file. All code must be written to files via the tool.
- ALWAYS run tests after writing code to verify correctness.
- Emit exactly ONE tool call per response. Wait for the result before continuing.
- When the task is fully complete and tests pass, emit <done> on its own line.
"""


REVIEWER_SYSTEM_PROMPT = """You are a strict Code Reviewer AI.
Given a task description, the target file, and the code generated by the Coder, you must verify if the code is correct, complete, and satisfies the task.
You must classify your findings into one of these severities:
- CRITICAL: Syntax errors, missing imports, crashes. (Verdict: REQUEST_CHANGES)
- MAJOR: Missing requirements, logic bugs. (Verdict: REQUEST_CHANGES)
- MINOR: Naming conventions, missing docstrings. (Verdict: APPROVE)
- RECOMMENDATION: Best practices, performance tweaks. (Verdict: APPROVE)

If there are CRITICAL or MAJOR issues, respond with "REQUEST_CHANGES" followed by a concise explanation.
If there are only MINOR, RECOMMENDATION, or no issues, respond with "APPROVE" followed by optional notes.
Do not write the fixed code yourself.
"""

def query_model(base_url: str, system_prompt: str, user_prompt: str = None, messages: list = None, model_name: str = CODER_MODEL, engine: str = CODER_ENGINE, vector: str = None, alpha: float = 1.0, layer: int = 16, max_retries: int = 3, max_tokens: int = 2048) -> str:
    msg_array = messages if messages is not None else [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]
    if engine == "mlx":
        log_trace(f"Querying persistent MLX Server for {model_name}...")
        payload = {
            "model": model_name,
            "messages": msg_array,
            "max_tokens": max_tokens,
            "temperature": 0.2
        }
        url = f"{base_url.rstrip('/')}/chat/completions"
        for attempt in range(1, max_retries + 1):
            start_time = time.time()
            try:
                req = Request(url, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"})
                with urlopen(req, timeout=300) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    elapsed = time.time() - start_time
                    msg = data["choices"][0].get("message", {})
                    resp_text = msg.get("content") or msg.get("reasoning") or ""
                    log_trace(f"Response from MLX Server in {elapsed:.2f}s ({len(resp_text)} chars)")
                    return resp_text
            except Exception as e:
                elapsed = time.time() - start_time
                log_trace(f"Attempt {attempt}/{max_retries} MLX API failed after {elapsed:.2f}s: {e}")
                print(f"⚠️ [Attempt {attempt}/{max_retries}] MLX query failed ({e}).", flush=True)
                if attempt < max_retries:
                    time.sleep(2)
                
        print(f"❌ [Orchestrator Error] All {max_retries} attempts to contact MLX Server failed.", flush=True)
        raise RuntimeError(f"All {max_retries} attempts to contact MLX Server failed.")
        
    if engine in ("openrouter", "openai", "litellm"):
        log_trace(f"Querying {engine.upper()} API for {model_name}...")
        payload = {
            "model": model_name,
            "messages": msg_array,
            "max_tokens": max_tokens,
            "temperature": 0.2
        }
        url = f"{base_url.rstrip('/')}/chat/completions"
        api_key = os.environ.get("OPENROUTER_API_KEY", "") if engine == "openrouter" else os.environ.get("OPENAI_API_KEY", "")
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
            if engine == "openrouter":
                headers["HTTP-Referer"] = "http://localhost:8800"
                headers["X-Title"] = "Terminal-Bench-Orchestrator"

        actual_max_retries = 10 if engine == "openrouter" else max_retries
        for attempt in range(1, actual_max_retries + 1):
            start_time = time.time()
            try:
                req = Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers)
                with urlopen(req, timeout=300) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    elapsed = time.time() - start_time
                    msg = data["choices"][0].get("message", {})
                    resp_text = msg.get("content") or msg.get("reasoning") or ""
                    log_trace(f"Response from {engine} in {elapsed:.2f}s ({len(resp_text)} chars)")
                    return resp_text
            except urllib.error.HTTPError as e:
                elapsed = time.time() - start_time
                if e.code in (402, 429):
                    log_trace(f"Attempt {attempt}/{actual_max_retries} {engine} API failed: {e}")
                    print(f"⚠️ [Orchestrator] OpenRouter Limit Reached ({e.code}). Hot-swapping to Local MLX Fallback!", flush=True)
                    # Instant seamless fallback to local M-Series model
                    return query_model(
                        base_url="http://localhost:8801/v1",
                        system_prompt=system_prompt,
                        user_prompt=user_prompt,
                        messages=messages,
                        model_name="mlx-community/Nanbeige4.1-3B-heretic-4bit",
                        engine="mlx",
                        vector=vector,
                        alpha=alpha,
                        layer=layer,
                        max_retries=3,
                        max_tokens=max_tokens
                    )
                else:
                    log_trace(f"Attempt {attempt}/{actual_max_retries} {engine} API failed after {elapsed:.2f}s: {e}")
                    print(f"⚠️ [Attempt {attempt}/{actual_max_retries}] {engine} query failed ({e}).", flush=True)
                    if attempt < actual_max_retries:
                        time.sleep(2)
            except Exception as e:
                elapsed = time.time() - start_time
                log_trace(f"Attempt {attempt}/{actual_max_retries} {engine} API failed after {elapsed:.2f}s: {e}")
                print(f"⚠️ [Attempt {attempt}/{actual_max_retries}] {engine} query failed ({e}).", flush=True)
                if attempt < actual_max_retries:
                    time.sleep(2)
                
        print(f"❌ [Orchestrator Error] All {actual_max_retries} attempts to contact {engine} failed.", flush=True)
        raise RuntimeError(f"All {actual_max_retries} attempts to contact {engine} failed.")

        
    # Ollama engine: use /api/chat for proper message handling
    url = base_url.replace("/v1", "") + "/api/chat"
    
    payload = {
        "model": model_name,
        "messages": msg_array,
        "stream": False,
        "options": {
            "temperature": 0.2,
            "num_predict": max_tokens
        },
        "keep_alive": "5m"
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
                msg = data.get("message", {})
                resp_text = msg.get("content") or msg.get("thinking") or ""
                resp_text = resp_text.strip()
                log_trace(f"Response from {model_name} in {elapsed:.2f}s ({len(resp_text)} chars)")
                return resp_text
        except Exception as e:
            elapsed = time.time() - start_time
            log_trace(f"Attempt {attempt}/{max_retries} failed after {elapsed:.2f}s: {e}")
            print(f"⚠️ [Attempt {attempt}/{max_retries}] Model query timed out or failed ({e}).", flush=True)
            if attempt < max_retries:
                time.sleep(2)
            
    print(f"❌ [Orchestrator Error] All {max_retries} attempts to contact model server failed.", flush=True)
    raise RuntimeError(f"All {max_retries} attempts to contact model server failed.")

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
    # 1. Deterministic Syntax/Compile Check
    try:
        import subprocess
        result = subprocess.run(["python", "-m", "py_compile", target_file], capture_output=True, text=True, timeout=10)
        if result.returncode != 0:
            return f"CRITICAL: SyntaxError/CompileError:\\n{result.stderr}"
    except Exception as e:
        pass # Fallback to LLM if py_compile fails to run
    
    # 2. Semantic LLM Review
    print(f"   🕵️‍♀️  [Checker] Reviewing code for semantic correctness...", flush=True)
    prompt = f"Task: {desc}\nTarget File: {target_file}\nGenerated Code:\n```python\n{code}\n```\nVerify if this code fulfills the task."
    review = query_model(REVIEWER_URL, REVIEWER_SYSTEM_PROMPT, prompt, model_name=REVIEWER_MODEL, engine=REVIEWER_ENGINE, max_tokens=1024)
    
    if "APPROVE" in review.upper()[:20] or "PASSED" in review.upper()[:20]:
        return "PASSED"
    return review

def check_command_safety(cmd: str) -> bool:
    """Pre-execution safety floor using 2-tier SafetyGate."""
    guard = evaluate_tool_call("bash", {"command": cmd})
    return guard.decision != "deny"

class EventEmitter:
    def __init__(self):
        self._listeners = {}

    def on(self, event_name: str, callback):
        if event_name not in self._listeners:
            self._listeners[event_name] = []
        self._listeners[event_name].append(callback)

    def emit(self, event_name: str, *args, **kwargs):
        for callback in self._listeners.get(event_name, []):
            callback(*args, **kwargs)

class ToolRegistry:
    def __init__(self):
        self._tools = {}

    def register(self, name: str, handler):
        self._tools[name] = handler

    def execute(self, call: ToolCall, context: dict) -> str:
        if call.name in self._tools:
            return self._tools[call.name](call.args, context)
        return f"ERROR: Unknown tool '{call.name}'"

# Global registry and event emitter
tool_registry = ToolRegistry()
event_emitter = EventEmitter()

def _safe_path(path: str, workspace_root: str) -> str:
    abs_path = os.path.abspath(path)
    clean_ws = os.path.abspath(workspace_root)
    if not (abs_path == clean_ws or abs_path.startswith(clean_ws + os.sep)):
        raise PermissionError(f"Path '{path}' is outside the workspace boundary.")
    return abs_path

def _handle_run_command(args, context):
    cmd = str(args.get("command", args.get("cmd", args.get("raw_arg", ""))))
    is_daemon = bool(args.get("is_daemon", False))
    if not check_command_safety(cmd):
        return "ERROR: Command blocked by safety floor."
        
    if context.get("interactive", False):
        print(f"   ⚠️  [Approval Gate] Agent wants to run: `{cmd}`", flush=True)
        resp = input("   Approve execution? (y/N): ")
        if resp.lower() not in ('y', 'yes'):
            return "ERROR: Command execution denied by user."
            
    print(f"   🏃 [Shell] {cmd}{' (Daemon)' if is_daemon else ''}", flush=True)
    sandbox = context["sandbox"]
    if is_daemon:
        task_id = sandbox.run_background_command(cmd)
        return f"Background task started with ID: {task_id}"
    else:
        exit_code, stdout, stderr = sandbox.run_command(cmd, timeout=120)
        result = f"Exit code: {exit_code}\\n"
        if stdout.strip():
            result += f"stdout:\\n{stdout[-3000:]}\\n"
        if stderr.strip():
            result += f"stderr:\\n{stderr[-2000:]}\\n"
        return result

def _handle_manage_task(args, context):
    action = str(args.get("action", ""))
    task_id = str(args.get("task_id", ""))
    if not action or not task_id:
        return "ERROR: manage_task requires action and task_id."
    return context["sandbox"].manage_task(task_id, action)

def _handle_write_file(args, context):
    filepath = str(args.get("path", args.get("file_path", args.get("filename", ""))))
    content = str(args.get("content", args.get("text", args.get("code", ""))))
    if not filepath:
        return "ERROR: write_file requires 'path' and 'content'"
    abs_path = _safe_path(filepath, context["workspace_root"])
    os.makedirs(os.path.dirname(abs_path) if os.path.dirname(abs_path) else ".", exist_ok=True)
    with open(abs_path, "w") as f:
        f.write(content)
    return f"Successfully wrote {len(content)} chars to {filepath}"

def _handle_replace_file_content(args, context):
    filepath = str(args.get("path", args.get("file_path", "")))
    try:
        start_line = int(args.get("start_line", 1))
        end_line = int(args.get("end_line", 1))
    except (ValueError, TypeError):
        return "ERROR: start_line and end_line must be integers."
    replacement_content = str(args.get("replacement_content", args.get("content", "")))
    
    if not filepath:
        return "ERROR: replace_file_content requires path, start_line, end_line, replacement_content"
    abs_path = _safe_path(filepath, context["workspace_root"])
    if not os.path.exists(abs_path):
        return f"ERROR: File '{filepath}' does not exist."
        
    with open(abs_path, "r") as f:
        lines = f.readlines()
        
    if start_line < 1 or end_line < start_line:
        return "ERROR: Invalid line range."
        
    prefix = lines[:start_line - 1]
    suffix = lines[end_line:] if end_line <= len(lines) else []
    
    if replacement_content and not replacement_content.endswith('\\n'):
        replacement_content += '\\n'
        
    new_lines = prefix + [replacement_content] + suffix
    
    with open(abs_path, "w") as f:
        f.writelines(new_lines)
        
    return f"Successfully replaced lines {start_line}-{end_line} in {filepath}"

def _handle_read_file(args, context):
    filepath = str(args.get("path", args.get("file_path", args.get("raw_arg", ""))))
    if not filepath:
        return "ERROR: read_file requires 'path'"
    abs_path = _safe_path(filepath, context["workspace_root"])
    if not os.path.exists(abs_path):
        return f"ERROR: File '{filepath}' does not exist."
    with open(abs_path, "r") as f:
        fc = f.read()
    if len(fc) > 4000:
        return fc[:2000] + "\\n\\n...[TRUNCATED]...\\n\\n" + fc[-2000:]
    return fc

def _handle_list_dir(args, context):
    dirpath = str(args.get("path", args.get("dirpath", args.get("raw_arg", "."))))
    abs_path = _safe_path(dirpath, context["workspace_root"])
    if not os.path.exists(abs_path):
        return f"ERROR: Directory '{dirpath}' does not exist."
    entries = os.listdir(abs_path)
    return "\\n".join(sorted(entries))

def _handle_update_plan(args, context):
    new_tasks = args.get("new_tasks", [])
    if not isinstance(new_tasks, list):
        return "ERROR: new_tasks must be a JSON array of task objects."
    task_graph = context.get("task_graph")
    current_task_idx = context.get("current_task_idx")
    if task_graph is not None and current_task_idx is not None:
        del task_graph[current_task_idx + 1:]
        task_graph.extend(new_tasks)
        try:
            with open("task_graph.json", "w") as f:
                json.dump({"goal": "Dynamically updated", "tasks": task_graph}, f, indent=2)
        except Exception:
            pass
        # Sync MarkdownTaskLedger / Plans.md
        for t in new_tasks:
            task_ledger.add_task(TaskSpec(
                task_id=f"T{t.get('step_id', len(task_ledger.get_all_tasks()) + 1):02d}",
                description=t.get("description", ""),
                target_files=[t.get("target_file")] if t.get("target_file") else [],
                dependencies=[],
                test_cmd=t.get("test_cmd", ""),
                status="pending"
            ))
        return f"Successfully updated plan. {len(new_tasks)} new tasks queued."
    return "ERROR: task_graph context not available."

tool_registry.register("run_command", _handle_run_command)
tool_registry.register("bash", _handle_run_command)
tool_registry.register("manage_task", _handle_manage_task)
tool_registry.register("write_file", _handle_write_file)
tool_registry.register("replace_file_content", _handle_replace_file_content)
tool_registry.register("edit_file", _handle_replace_file_content)
tool_registry.register("read_file", _handle_read_file)
tool_registry.register("list_dir", _handle_list_dir)
tool_registry.register("update_plan", _handle_update_plan)
tool_registry.register("find_definition", handle_find_definition)
tool_registry.register("find_references", handle_find_references)
tool_registry.register("document_symbols", handle_document_symbols)
tool_registry.register("hover", handle_hover)

def derive_messages(ledger, base_messages: list, from_seq: int = 0) -> list:
    """Projects the current state of the model context strictly from the SessionEvent append-only log."""
    events = ledger.replay(from_seq)
    
    # Collect all sequence numbers of tool results evicted by Tier 1 compaction
    evicted_seqs = set()
    for event in events:
        if event.event_type == "compaction/evict_tools":
            evicted_seqs.update(event.payload.get("evicted_seqs", []))

    messages = list(base_messages)
    for event in events:
        if event.event_type == "compaction/checkpoint":
            # Tier 2 summary checkpoint: condense preceding context cleanly
            messages = list(base_messages)
            messages.append({"role": "user", "content": f"[SYSTEM: CONTEXT COMPACTED SUMMARY CHECKPOINT]:\n{event.payload.get('summary', '')}"})
        elif event.event_type == "user/prompt":
            messages.append({"role": "user", "content": event.payload.get("content", "")})
        elif event.event_type == "assistant/message":
            messages.append({"role": "assistant", "content": event.payload.get("full_content", event.payload.get("content", ""))})
        elif event.event_type == "tool/result":
            if event.seq in evicted_seqs:
                call_sig = str(event.payload.get("call", ""))[:40]
                placeholder = f"[Tool Output Evicted - Ref #{event.seq} ({call_sig}) - Full output archived in telemetry]"
                messages.append({"role": "user", "content": f"You called:\n{event.payload.get('call', '')}\n\nResult:\n{placeholder}"})
            else:
                messages.append({"role": "user", "content": f"You called:\n{event.payload.get('call', '')}\n\nResult:\n{event.payload.get('output', '')}"})
        elif event.event_type == "tool/error":
            messages.append({"role": "user", "content": f"Tool error:\n{event.payload.get('error', '')}"})
        elif event.event_type == "system/update":
            # Some models don't support mid-conversation system roles, so we wrap it as a user message
            messages.append({"role": "user", "content": f"[System Update]: {event.payload.get('message', '')}"})
        elif event.event_type == "parser/error":
            messages.append({"role": "user", "content": event.payload.get("message", "")})
    return messages

def run_task_graph(goal: str, vector: str = None, alpha: float = 1.0, layer: int = 16, interactive: bool = False):
    workspace_root = os.path.abspath(os.getcwd())
    print(f"\n{'='*60}", flush=True)
    print(f"🚀 Multi-Agent Orchestrator Starting Goal:", flush=True)
    print(f"   \"{goal}\"", flush=True)
    if vector:
        print(f"   🎛️ Active Steering: Vector='{vector}', Alpha={alpha}, Layer=L{layer}", flush=True)
    print(f"{'='*60}\n", flush=True)

    # Phase 0: Incremental AST Static Repo Map (Tier A Code Intelligence)
    context_str = ""
    try:
        sym_index = get_symbol_index(workspace_root)
        sym_index.scan_workspace()
        repo_map = sym_index.get_condensed_repo_map(max_tokens=1000)
        if repo_map:
            print(f"🗺️  [Symbol Index] Injected static repository symbol map ({len(sym_index.definitions)} defs indexed).", flush=True)
            context_str = repo_map
    except Exception as e:
        print(f"   ⚠️ Symbol indexing note: {e}", flush=True)

    # Phase 4.1: FAISS Semantic Context Retrieval (Optional domain lookup)
    print("🔍 [0/2] P3 FAISS Worker retrieving workspace context... (SKIPPED FOR 16GB RAM MODE)", flush=True)
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
    log_trace("FAISS Retrieval step skipped (16GB RAM mode)")

    CHECKPOINT_FILE = "harness_checkpoint.json"
    start_task_idx = 0
    session_id = None
    
    if os.path.exists(CHECKPOINT_FILE):
        try:
            with open(CHECKPOINT_FILE, "r") as f:
                ckpt = json.load(f)
            if ckpt.get("goal") == goal:
                session_id = ckpt.get("session_id")
                start_task_idx = ckpt.get("completed_step", 0)
                print(f"   🔄 [Resuming] Recovered session {session_id} from crash. Jumping to step {start_task_idx + 1}...", flush=True)
        except Exception:
            pass

    import uuid
    if not session_id:
        session_id = uuid.uuid4().hex[:8]
        
    runs_dir = Path("runs")
    runs_dir.mkdir(parents=True, exist_ok=True)
    ledger = JSONLSessionLedger(runs_dir / f"session_{session_id}.jsonl", session_id=session_id)
    task_ledger = MarkdownTaskLedger("Plans.md")
    compactor_gov = CompactionGovernor(token_limit=16000, trigger_ratio=0.85)

    if start_task_idx == 0:
        ledger.append(SessionEvent(event_type="goal/start", payload={"goal": goal, "vector": vector, "alpha": alpha}))
        
        # Instruction Governance (Reporails Native Integration)
        from core.instruction_governance import ReporailsLinter
        linter = ReporailsLinter()
        findings = linter.lint_workspace(os.getcwd(), CODER_SYSTEM_PROMPT)
        
        if findings:
            print("⚠️  [Reporails] Instruction Governance Failed:", flush=True)
            has_error = False
            for f in findings:
                print(f"  [{f.severity.upper()}] {f.message} (Rule: {f.rule_id})", flush=True)
                if f.severity == "error":
                    has_error = True
            
            if has_error and not interactive:
                print("❌ [Reporails] Aborting run due to 'error' level governance failures. Fix vague instructions or use --interactive to override.", flush=True)
                return

    planner_model = os.environ.get("PLANNER_MODEL", "Ling-3.0")
    print(f"🧠 [1/2] {planner_model} (Planner) generating task graph...", flush=True)
    print(f"   ↳ backend: {PLANNER_MODEL}", flush=True)
    
    full_planner_prompt = f"User Goal: {goal}"
    if context_str:
        full_planner_prompt += f"\n\nRetrieved Workspace Context:\n{context_str}\n"

    if start_task_idx > 0 and os.path.exists("task_graph.json"):
        with open("task_graph.json", "r") as f:
            task_graph = json.load(f).get("tasks", [])
        print(f"   ✅ Loaded {len(task_graph)} subtasks from existing plan.", flush=True)
    else:
        task_graph = None
        current_prompt = full_planner_prompt
        MAX_PLANNER_RETRIES = 3
        
        for planner_attempt in range(1, MAX_PLANNER_RETRIES + 1):
            if planner_attempt > 1:
                print(f"   🔄 [Planner Attempt {planner_attempt}/{MAX_PLANNER_RETRIES}] Retrying with JSON format enforcement...", flush=True)
            
            planner_response = query_model(PLANNER_URL, PLANNER_SYSTEM_PROMPT, current_prompt, model_name=PLANNER_MODEL, engine=PLANNER_ENGINE, vector=vector, alpha=alpha, layer=layer)
            
            task_graph = extract_json_array(planner_response)
            if task_graph and isinstance(task_graph, list) and len(task_graph) > 0:
                print(f"✅ Planned {len(task_graph)} subtasks on attempt {planner_attempt}.", flush=True)
                break
            
            # Log failure with raw snippet
            print(f"   ⚠️ [Planner Attempt {planner_attempt}] Failed to parse JSON array from response ({len(planner_response)} chars).", flush=True)
            ledger.append(SessionEvent(event_type="error", payload={"stage": "planner", "attempt": planner_attempt, "raw_snippet": planner_response[:300]}))
            
            current_prompt = (
                f"Your previous response could not be parsed as a JSON array.\n"
                f"You MUST respond ONLY with a raw JSON array of objects without markdown fences, explanation, or conversational text.\n\n"
                f"Example format:\n"
                f"[\n"
                f"  {{\"step_id\": 1, \"description\": \"Implement CLI in taskmaster.py\", \"target_file\": \"taskmaster.py\", \"test_cmd\": \"python3 taskmaster.py --help\"}}\n"
                f"]\n\n"
                f"Original Goal: {goal}"
            )
        
        if not task_graph or not isinstance(task_graph, list):
            print(f"   ⚠️ Planner decomposition exhausted. Synthesizing default atomic task graph from goal...", flush=True)
            import re
            files = re.findall(r'[\w\-]+\.py', goal)
            target = files[0] if files else "main.py"
            task_graph = [{
                "step_id": 1,
                "description": goal,
                "target_file": target,
                "test_cmd": "pytest" if "pytest" in goal else f"python3 -m py_compile {target}"
            }]
            ledger.append(SessionEvent(event_type="planner/fallback_atomic", payload={"task_graph": task_graph}))
            print(f"✅ Synthesized {len(task_graph)} default atomic task.", flush=True)
    
        update_state_memory(goal, task_graph, -1, "Planned tasks")
    
        # Populate Plans.md via TaskLedger
        for t in task_graph:
            task_ledger.add_task(TaskSpec(
                task_id=f"T{t.get('step_id', len(task_ledger.get_all_tasks()) + 1):02d}",
                description=t.get("description", ""),
                target_files=[t.get("target_file")] if t.get("target_file") else [],
                dependencies=[f"T{t.get('step_id')-1:02d}"] if t.get("step_id", 1) > 1 else [],
                test_cmd=t.get("test_cmd", ""),
                status="pending"
            ))

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
    
    try:
        for i, task in enumerate(task_graph):
            if i < start_task_idx:
                # Update ledger to reflect we skipped it via checkpoint
                task_tid = f"T{task.get('step_id', i+1):02d}"
                task_ledger.update_status(task_tid, "done")
                continue
            
            step_id = task.get("step_id")
            task_tid = f"T{step_id:02d}"
            desc = task.get("description")
            target_file = task.get("target_file")
            test_cmd = task.get("test_cmd")

            task_ledger.update_status(task_tid, "in_progress")
            turn_start_seq = ledger.append(SessionEvent(event_type="turn/start", payload={"step_id": step_id, "task_id": task_tid, "description": desc}))

            print(f"\\n💻 [2/2] Agent executing Step {step_id}: {desc}", flush=True)
            print(f"   ↳ backend: {CODER_MODEL}", flush=True)
            update_state_memory(goal, task_graph, i, f"Working on step {step_id}")
            
            # Save WIP state before starting execution
            compactor_gov.pre_compact(
                session_id=session_id,
                current_idx=i,
                active_task_id=task_tid,
                tasks=task_graph,
                active_diffs=f"Task {step_id}: {desc}",
                ledger_seq=ledger._seq
            )

            # Phase 3: OpenCode Context Epoch Setup
            # Base prompt is pure instruction
            base_messages = [
                {"role": "system", "content": CODER_SYSTEM_PROMPT}
            ]
            
            # Emit dynamic context as system/update events AFTER turn start to project them cleanly
            if target_file:
                ledger.append(SessionEvent(event_type="system/update", payload={"message": f"Target File for this task: {target_file}"}))
            if test_cmd:
                ledger.append(SessionEvent(event_type="system/update", payload={"message": f"Verification Command for this task: {test_cmd}"}))
            
            completed_tasks = [t for t in task_graph if task_ledger._tasks.get(f"T{t.get('step_id', 0):02d}", None) and task_ledger._tasks[f"T{t.get('step_id', 0):02d}"].status == "done"]
            recent_completed = completed_tasks[-3:]
            if recent_completed:
                comp_text = "\\n".join([f"- Step {ct.get('step_id')}: {ct.get('description')}" for ct in recent_completed])
                ledger.append(SessionEvent(event_type="system/update", payload={"message": f"Recent Completed Tasks:\\n{comp_text}"}))
                
            ledger.append(SessionEvent(event_type="system/update", payload={"message": "Hint: Use `list_dir` and `read_file` to explore the workspace files as needed."}))

            
            # Inject relevant JIT skills
            try:
                from skill_procurer import SkillProcurer
                skill_content = SkillProcurer().get_skill_content(desc)
                if skill_content:
                    ledger.append(SessionEvent(event_type="system/update", payload={"message": f"Injected JIT Skill Context:\\n{skill_content}"}))
            except Exception:
                pass
            
            # Emit the formal user prompt (Admitted Prompt in OpenCode terminology)
            admitted_prompt = f"Please execute Task {step_id}: {desc}"
            ledger.append(SessionEvent(event_type="user/prompt", payload={"role": "user", "content": admitted_prompt}))
            
            # ReAct Loop: agent acts, observes, iterates
            MAX_REACT_STEPS = 15
            task_complete = False
            
            for step in range(1, MAX_REACT_STEPS + 1):
                print(f"   🔄 [ReAct Step {step}/{MAX_REACT_STEPS}]", flush=True)
                ledger.append(SessionEvent(event_type="step/start", payload={"step": step, "task_id": task_tid}))
                
                # Derive exact model context from the ledger
                messages = derive_messages(ledger, base_messages, from_seq=turn_start_seq)
                
                # Middleware: pre-step
                event_emitter.emit("agent/pre-step", messages=messages, step=step)
                
                # Query model
                event_emitter.emit("agent/request", messages=messages)
                raw_output = query_model(CODER_URL, CODER_SYSTEM_PROMPT, messages=messages, model_name=CODER_MODEL, engine=CODER_ENGINE, max_tokens=4096)
                
                # Middleware: llm/stream (simulated)
                event_emitter.emit("llm/stream", output=raw_output)
                
                ledger.append(SessionEvent(event_type="assistant/message", payload={"content": raw_output[:500], "full_content": raw_output}))
                
                # Check if agent signals completion
                if "<done>" in raw_output.lower():
                    print(f"   ✅ Agent signaled task complete.", flush=True)
                    task_complete = True
                    break
                
                # Multi-grammar tool parsing
                parsed_calls, parse_errors = parse_tool_calls_from_text(raw_output)
                if parsed_calls:
                    # Phase 4: Parallelize Read-Only Tools (including AST/LSP)
                    read_tools = {"read_file", "list_dir", "grep_search", "find_definition", "find_references", "document_symbols", "hover"}
                    read_calls = [c for c in parsed_calls if c.name in read_tools]
                    write_calls = [c for c in parsed_calls if c.name not in read_tools]
                    
                    context = {"sandbox": sandbox, "workspace_root": workspace_root, "task_graph": task_graph, "current_task_idx": i, "interactive": interactive}
                    
                    def _exec_tool(call):
                        print(f"   🛠️  [Tool] {call.name}({str(call.args)[:60]}...)", flush=True)
                        event_emitter.emit("tool/call", call=call)
                        tool_result = tool_registry.execute(call, context)
                        comp_result, saved = compress_text(tool_result)
                        if saved > 0:
                            print(f"   🗜️ Compressed tool output by {saved} chars.", flush=True)
                        return call, comp_result
                    
                    # 1. Execute read calls concurrently
                    if read_calls:
                        from concurrent.futures import ThreadPoolExecutor, as_completed
                        with ThreadPoolExecutor(max_workers=5) as executor:
                            future_to_call = {executor.submit(_exec_tool, call): call for call in read_calls}
                            for future in as_completed(future_to_call):
                                call = future_to_call[future]
                                try:
                                    _, comp_result = future.result()
                                    ledger.append(SessionEvent(event_type="tool/call", payload={"tool": call.name, "args": call.args}))
                                    ledger.append(SessionEvent(event_type="tool/result", payload={"call": f"{call.name}({call.args})", "output": comp_result}))
                                except Exception as e:
                                    print(f"   ❌ Tool error: {e}", flush=True)
                                    ledger.append(SessionEvent(event_type="tool/error", payload={"error": str(e)}))
                                    
                    # 2. Execute write calls sequentially
                    for call in write_calls:
                        try:
                            ledger.append(SessionEvent(event_type="tool/call", payload={"tool": call.name, "args": call.args}))
                            _, comp_result = _exec_tool(call)
                            ledger.append(SessionEvent(event_type="tool/result", payload={"call": f"{call.name}({call.args})", "output": comp_result}))
                        except Exception as e:
                            print(f"   ❌ Tool error: {e}", flush=True)
                            ledger.append(SessionEvent(event_type="tool/error", payload={"error": str(e)}))

                    # In-Loop Dynamic Compaction Check (Tier 1 clear_tool_uses & Tier 2 checkpoint)
                    compact_stats = compactor_gov.evaluate_in_loop_compaction(
                        ledger=ledger,
                        turn_start_seq=turn_start_seq,
                        current_messages=messages
                    )
                    if compact_stats.get("tier1_evictions", 0) > 0:
                        print(f"   🗜️ [In-Loop Compaction] Tier 1 evicted {compact_stats['tier1_evictions']} stale tool payload(s).", flush=True)
                    if compact_stats.get("tier2_triggered", False):
                        print(f"   🧠 [In-Loop Compaction] Tier 2 injected 5-section context checkpoint.", flush=True)
                elif parse_errors:
                    err_msg = '\n'.join(parse_errors)
                    print(f"   ❌ [Parser] Syntax error detected, injecting feedback loop...", flush=True)
                    ledger.append(SessionEvent(event_type="parser/error", payload={"message": f"System Error: Failed to parse your tool call. Errors:\n{err_msg}\n\nPlease format your tool call as: <execute>tool_name(param1=\"value1\", param2=\"value2\")</execute> and try again."}))
                else:
                    ledger.append(SessionEvent(event_type="parser/error", payload={"message": "Please take an action using an available tool inside <execute>tool_name(...)</execute>, or emit <done> if the task is complete."}))
            
            if not task_complete:
                print(f"   ⚠️ Max ReAct steps reached for Step {step_id}. Moving on.", flush=True)
                task_ledger.update_status(task_tid, "blocked")
            else:
                task_ledger.update_status(task_tid, "done")
            
            # Final quality gate: Checker reviews what was produced
            if target_file and os.path.exists(target_file):
                try:
                    with open(target_file, "r") as f:
                        final_code = f.read()
                    review = evaluate_code(final_code, desc, target_file)
                    if review == "PASSED":
                        print(f"   ✅ [Checker] Final review: PASSED", flush=True)
                        ledger.append(SessionEvent(event_type="review/result", payload={"verdict": "PASSED", "target_file": target_file}))
                    else:
                        print(f"   ⚠️ [Checker] Final review requested changes: {review.splitlines()[0][:100]}", flush=True)
                        log_dpo_pair(desc, final_code, "", review)
                        
                        # Multi-turn Self-Healing Repair Attempt (up to 3 iterations)
                        MAX_REPAIR_ATTEMPTS = 3
                        current_review = review
                        for repair_attempt in range(1, MAX_REPAIR_ATTEMPTS + 1):
                            print(f"   🔧 [Self-Healing {repair_attempt}/{MAX_REPAIR_ATTEMPTS}] Re-dispatching to Coder to fix review critique...", flush=True)
                            with open(target_file, "r") as f:
                                current_code = f.read()
                            repair_prompt = f"The Code Reviewer reviewed your target file '{target_file}' and requested changes:\\n\\nReviewer Feedback:\\n{current_review}\\n\\nCurrent Code in {target_file}:\\n```python\\n{current_code}\\n```\\n\\nPlease fix the issues and write the updated code to '{target_file}' using write_file."
                            repair_base_messages = [{"role": "system", "content": CODER_SYSTEM_PROMPT}, {"role": "user", "content": repair_prompt}]
                            raw_repair = query_model(CODER_URL, CODER_SYSTEM_PROMPT, messages=repair_base_messages, model_name=CODER_MODEL, engine=CODER_ENGINE, max_tokens=4096)
                            repair_calls, repair_errors = parse_tool_calls_from_text(raw_repair)
                            if repair_calls:
                                for rcall in repair_calls:
                                    context = {"sandbox": sandbox, "workspace_root": workspace_root, "task_graph": task_graph, "current_task_idx": i, "interactive": interactive}
                                    tool_registry.execute(rcall, context)
                                if os.path.exists(target_file):
                                    with open(target_file, "r") as f:
                                        repaired_code = f.read()
                                    re_review = evaluate_code(repaired_code, desc, target_file)
                                    if re_review == "PASSED":
                                        print(f"   ✅ [Checker] Post-repair review: PASSED (attempt {repair_attempt})", flush=True)
                                        ledger.append(SessionEvent(event_type="review/result", payload={"verdict": "PASSED_AFTER_REPAIR", "target_file": target_file, "attempt": repair_attempt}))
                                        break
                                    else:
                                        current_review = re_review
                            elif repair_errors:
                                print(f"   ⚠️ [Self-Healing] Parsing errors during repair: {repair_errors}", flush=True)
                except Exception as e:
                    print(f"   ⚠️ [Checker] Could not review {target_file}: {e}", flush=True)
            
            # Save checkpoint after each completed task
            try:
                checkpoint = {
                    "goal": goal,
                    "session_id": session_id,
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
        clear_wip_state()


    update_state_memory(goal, task_graph, len(task_graph), "Execution Complete")
    
    print(f"   📝 Generating completion report...", flush=True)
    completion_report = f"# Completion Report: {goal}\n\n"
    for task in task_graph:
        tid = f"T{task.get('step_id', 0):02d}"
        t_status = task_ledger._tasks[tid].status if tid in task_ledger._tasks else "unknown"
        verdict = "PASSED" if t_status == "done" else "FAILED"
        completion_report += f"## Task {task.get('step_id')}: {task.get('description')}\n"
        completion_report += f"- **Target File**: {task.get('target_file', 'N/A')}\n"
        test_cmd = task.get('test_cmd')
        if test_cmd:
            completion_report += f"- **Validation Cmd**: `{test_cmd}`\n"
        completion_report += f"- **Status**: {t_status.upper()}\n"
        completion_report += f"- **Verdict**: {verdict}\n\n"
        
    try:
        with open("completion_report.md", "w") as f:
            f.write(completion_report)
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
    parser.add_argument("--interactive", action="store_true", help="Enable interactive approval gates for destructive commands")
    args = parser.parse_args()

    run_task_graph(args.goal, vector=args.vector, alpha=args.alpha, layer=args.layer, interactive=args.interactive)
