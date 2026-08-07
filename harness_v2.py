import os
import sys
import json
import time
import subprocess
import ast
from pathlib import Path
from typing import Dict, List, Any, Optional, Generator
from dataclasses import dataclass, asdict

# ============================================================================
# 1. DISCRIMINATED UNIONS & EVENT TYPES (Claude Code inspired)
# ============================================================================

@dataclass
class AgentEvent:
    event_type: str  # 'SESSION_START', 'TURN_START', 'TOOL_START', 'TOOL_END', 'EVAL_PASS', 'EVAL_FAIL', 'RECOVERY'
    payload: Dict[str, Any]
    timestamp: float = 0.0

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = time.time()

@dataclass
class TerminalResult:
    status: str  # 'COMPLETE', 'MAX_TURNS_EXCEEDED', 'BUDGET_EXHAUSTED', 'ABORTED', 'ERROR'
    summary: str
    total_turns: int
    total_duration_sec: float
    events_logged: int

# ============================================================================
# 2. TIERED MEMORY HIERARCHY
# ============================================================================

class MemoryManager:
    """
    Manages the 4-Tier Memory Hierarchy:
    - Tier 1: Project Conventions (PROJECT.md)
    - Tier 2: Reactive Session State (STATE.md)
    - Tier 3: Dynamic Adaptive Reminders (Modified files diff, git status)
    - Tier 4: DPO Preference Dataset (dpo_logs.jsonl)
    """
    def __init__(self, workspace_dir: Path):
        self.workspace_dir = workspace_dir
        self.project_md_path = workspace_dir / "PROJECT.md"
        self.state_md_path = workspace_dir / "STATE.md"
        self.dpo_log_path = workspace_dir / "dpo_logs.jsonl"

    def load_tier1_conventions(self) -> str:
        """Loads repository-level conventions (equivalent to CLAUDE.md)."""
        if self.project_md_path.exists():
            try:
                return self.project_md_path.read_text(encoding="utf-8").strip()
            except Exception:
                pass
        return "# Default Project Conventions: Follow PEP8 and test code."

    def update_tier2_state(self, goal: str, tasks: List[Dict[str, Any]], current_idx: int, message: str = ""):
        """Persists reactive task progress board."""
        content = f"# Reactive Agent State\n\n**Goal**: {goal}\n**Status**: {message}\n\n## Subtasks:\n"
        for i, t in enumerate(tasks):
            char = "x" if i < current_idx else ("/" if i == current_idx else " ")
            content += f"- [{char}] Step {t.get('step_id', i+1)}: {t.get('description', '')}\n"
        
        try:
            self.state_md_path.write_text(content, encoding="utf-8")
        except Exception:
            pass

    def build_tier3_adaptive_reminders(self, last_failing_code: Optional[str] = None, last_error: Optional[str] = None) -> str:
        """Constructs volatile dynamic reminders injected into each turn."""
        reminders = []
        if last_error:
            reminders.append(f"⚠️ [Last Error Traceback]: {last_error}")
        if last_failing_code:
            reminders.append(f"📄 [Previous Attempt]: Code failed verification. Ensure requirements are met without repeating mistakes.")
        return "\n".join(reminders)

    def log_tier4_dpo_pair(self, prompt: str, rejected: str, chosen: str, error: str):
        """Logs failure/chosen pair to the DPO flywheel."""
        entry = {
            "timestamp": time.time(),
            "prompt": prompt,
            "rejected": rejected,
            "chosen": chosen,
            "error": error
        }
        try:
            with self.dpo_log_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception:
            pass

# ============================================================================
# 3. UNIFIED TOOL STRATEGY PATTERN
# ============================================================================

class BaseTool:
    name: str = "base_tool"
    description: str = "Base tool description"

    def execute(self, params: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError

class FileWriteTool(BaseTool):
    name = "file_write"
    description = "Writes raw content to a file in the workspace."

    def execute(self, params: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        file_path = context["workspace_dir"] / params["target_file"]
        content = params["content"]
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
        return {"status": "SUCCESS", "bytes_written": len(content), "file": str(file_path)}

class ASTValidatorTool(BaseTool):
    name = "ast_validate"
    description = "Parses Python code to verify syntax before execution."

    def execute(self, params: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        code = params["code"]
        try:
            ast.parse(code)
            return {"status": "PASSED", "error": None}
        except SyntaxError as e:
            return {"status": "FAILED", "error": str(e)}

class ShellExecTool(BaseTool):
    name = "shell_exec"
    description = "Runs a sandboxed verification command."

    def execute(self, params: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        cmd = params["command"]
        start_t = time.time()
        res = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            cwd=str(context["workspace_dir"])
        )
        return {
            "status": "PASSED" if res.returncode == 0 else "FAILED",
            "returncode": res.returncode,
            "stdout": res.stdout,
            "stderr": res.stderr,
            "duration_sec": round(time.time() - start_t, 3)
        }

# ============================================================================
# 4. THE ASYNC GENERATOR AGENT LOOP ENGINE (query.ts style)
# ============================================================================

class AgentHarnessV2:
    """
    Industrial agent harness inspired by Claude Code's query.ts engine.
    Yields lifecycle events as an async-style event generator.
    """
    def __init__(self, workspace_dir: str = "/Users/adarrsh/workspace"):
        self.workspace_dir = Path(workspace_dir)
        self.memory = MemoryManager(self.workspace_dir)
        self.tools: Dict[str, BaseTool] = {
            "file_write": FileWriteTool(),
            "ast_validate": ASTValidatorTool(),
            "shell_exec": ShellExecTool()
        }

    def run_agent_loop(self, goal: str, tasks: List[Dict[str, Any]], max_turns_per_task: int = 3) -> Generator[AgentEvent, None, TerminalResult]:
        """
        Coroutines generator driving the agent heartbeat.
        Yields events in real-time and returns a final TerminalResult.
        """
        start_time = time.time()
        event_count = 0

        # 1. Load Tier 1 Conventions
        conventions = self.memory.load_tier1_conventions()
        yield AgentEvent("SESSION_START", {"goal": goal, "conventions_loaded": bool(conventions), "num_tasks": len(tasks)})
        event_count += 1

        for idx, task in enumerate(tasks):
            desc = task.get("description", "")
            target_file = task.get("target_file", "output.py")
            test_cmd = task.get("test_cmd", f"{sys.executable} -m py_compile {target_file}")
            
            self.memory.update_tier2_state(goal, tasks, idx, f"Working on Step {idx+1}")
            
            turn = 0
            last_code = None
            last_error = None
            task_success = False

            while turn < max_turns_per_task and not task_success:
                turn += 1
                
                # Dynamic Adaptive Reminders
                reminders = self.memory.build_tier3_adaptive_reminders(last_code, last_error)
                
                yield AgentEvent("TURN_START", {
                    "task_idx": idx,
                    "turn": turn,
                    "target_file": target_file,
                    "has_reminders": bool(reminders)
                })
                event_count += 1

                # Mock/Simulate Code Generation step in harness (or call local MLX model)
                # For demonstration, generate code that adheres to conventions
                candidate_code = f"# Auto-generated code for: {desc}\nimport os\n\ndef run():\n    return '{desc}'\n"
                
                # Step A: Validate AST
                yield AgentEvent("TOOL_START", {"tool": "ast_validate", "file": target_file})
                event_count += 1
                
                ast_res = self.tools["ast_validate"].execute({"code": candidate_code}, {"workspace_dir": self.workspace_dir})
                
                if ast_res["status"] != "PASSED":
                    last_error = ast_res["error"]
                    last_code = candidate_code
                    yield AgentEvent("EVAL_FAIL", {"reason": "AST_SYNTAX_ERROR", "error": last_error})
                    event_count += 1
                    continue

                # Step B: Write File
                yield AgentEvent("TOOL_START", {"tool": "file_write", "file": target_file})
                event_count += 1
                write_res = self.tools["file_write"].execute({"target_file": target_file, "content": candidate_code}, {"workspace_dir": self.workspace_dir})

                # Step C: Run Verification Command
                yield AgentEvent("TOOL_START", {"tool": "shell_exec", "command": test_cmd})
                event_count += 1
                shell_res = self.tools["shell_exec"].execute({"command": test_cmd}, {"workspace_dir": self.workspace_dir})

                if shell_res["status"] == "PASSED":
                    task_success = True
                    yield AgentEvent("EVAL_PASS", {"step_id": task.get("step_id", idx+1), "file": target_file})
                    event_count += 1
                    
                    # If this succeeded after a failure, log DPO pair
                    if last_code and last_error:
                        self.memory.log_tier4_dpo_pair(desc, last_code, candidate_code, last_error)
                        yield AgentEvent("RECOVERY", {"dpo_logged": True})
                        event_count += 1
                else:
                    last_error = shell_res["stderr"] or "Command failed"
                    last_code = candidate_code
                    yield AgentEvent("EVAL_FAIL", {"reason": "TEST_COMMAND_FAILED", "error": last_error})
                    event_count += 1

            if not task_success:
                self.memory.update_tier2_state(goal, tasks, idx, f"Failed at Step {idx+1}")
                return TerminalResult("ERROR", f"Task {idx+1} failed after {max_turns_per_task} turns.", idx+1, time.time() - start_time, event_count)

        self.memory.update_tier2_state(goal, tasks, len(tasks), "ALL TASKS COMPLETED")
        return TerminalResult("COMPLETE", "Goal achieved successfully.", len(tasks), time.time() - start_time, event_count)

# ============================================================================
# CLI Runner
# ============================================================================
if __name__ == "__main__":
    harness = AgentHarnessV2()
    sample_tasks = [
        {"step_id": 1, "description": "Create sample data module", "target_file": "sample_mod.py"}
    ]
    print("🚀 Initializing Claude-Code-Inspired SkillOpt Agent Harness v2...\n")
    
    # Run the generator loop
    runner = harness.run_agent_loop("Build sample data module with unit tests", sample_tasks)
    try:
        while True:
            event = next(runner)
            print(f"📡 [Event: {event.event_type}] {json.dumps(event.payload)}")
    except StopIteration as e:
        result: TerminalResult = e.value
        print(f"\n🎉 [Terminal Result]: {result.status} | Total Duration: {result.total_duration_sec:.2f}s | Events: {result.events_logged}")
