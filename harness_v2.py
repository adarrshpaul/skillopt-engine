import os
import sys
import json
import time
import subprocess
import ast
from pathlib import Path
from typing import Dict, List, Any, Optional, Generator
from dataclasses import dataclass

from web_crawler import WebScraperEngine

# ============================================================================
# 1. DISCRIMINATED UNIONS & EVENT TYPES
# ============================================================================

@dataclass
class AgentEvent:
    event_type: str  # 'SESSION_START', 'TURN_START', 'MODEL_SWITCH', 'TOOL_START', 'TOOL_END', 'EVAL_PASS', 'EVAL_FAIL', 'RECOVERY'
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
    active_model: str
    avg_ttft_ms: float
    avg_tokens_per_sec: float

# ============================================================================
# 2. DYNAMIC MODEL SWITCHER & REGISTRY
# ============================================================================

@dataclass
class ModelProfile:
    model_id: str
    display_name: str
    architecture: str
    active_params: str
    simulated_ttft_ms: float
    simulated_tokens_sec: float
    base_pass_rate: float
    description: str

class ModelRegistry:
    """
    Manages active model switching and profile dispatch.
    Supports Ling-3.0-flash, Nanbeige-3B, Gemma-4-12B, and Ornith-9B.
    """
    MODELS = {
        "ling-3.0-flash": ModelProfile(
            model_id="inclusionAI/Ling-3.0-flash",
            display_name="Ling-3.0-Flash (Fastest)",
            architecture="124B Sparse MoE (1/64)",
            active_params="5.1B",
            simulated_ttft_ms=310.0,
            simulated_tokens_sec=118.5,
            base_pass_rate=76.8,
            description="Ultra-fast sparse MoE with Mooncake hierarchical caching. Ideal for high-speed loops."
        ),
        "nanbeige-3b": ModelProfile(
            model_id="Nanbeige/Nanbeige4.2-3B",
            display_name="Nanbeige 4.2-3B (Compact)",
            architecture="Looped Dense Transformer",
            active_params="3.0B",
            simulated_ttft_ms=420.0,
            simulated_tokens_sec=88.3,
            base_pass_rate=68.1,
            description="Ultra-compact dense model. Fits in minimal VRAM with high reasoning density."
        ),
        "gemma-4-12b": ModelProfile(
            model_id="Google/Gemma-4-12B",
            display_name="Gemma 4 12B (Multimodal)",
            architecture="Encoder-Free Dense Multimodal",
            active_params="12.0B",
            simulated_ttft_ms=1250.0,
            simulated_tokens_sec=45.2,
            base_pass_rate=72.4,
            description="Encoder-free multimodal model for complex vision/code reasoning."
        ),
        "ornith-9b": ModelProfile(
            model_id="DeepReinforce/Ornith-1.0-9B",
            display_name="Ornith 1.0-9B (Local MLX)",
            architecture="Dense Transformer (Apple Silicon MLX)",
            active_params="9.0B",
            simulated_ttft_ms=750.0,
            simulated_tokens_sec=55.0,
            base_pass_rate=67.8,
            description="Offline default running natively on Mac GPU via MLX."
        )
    }

    def __init__(self, default_model: str = "ling-3.0-flash"):
        self.active_model_key = default_model.lower()
        if self.active_model_key not in self.MODELS:
            self.active_model_key = "ling-3.0-flash"

    def switch_model(self, model_key: str) -> ModelProfile:
        model_key = model_key.lower()
        if model_key in self.MODELS:
            self.active_model_key = model_key
        return self.get_active_profile()

    def get_active_profile(self) -> ModelProfile:
        return self.MODELS[self.active_model_key]

# ============================================================================
# 3. TIERED MEMORY HIERARCHY
# ============================================================================

class MemoryManager:
    def __init__(self, workspace_dir: Path):
        self.workspace_dir = workspace_dir
        self.project_md_path = workspace_dir / "PROJECT.md"
        self.state_md_path = workspace_dir / "STATE.md"
        self.dpo_log_path = workspace_dir / "dpo_logs.jsonl"

    def load_tier1_conventions(self) -> str:
        if self.project_md_path.exists():
            try:
                return self.project_md_path.read_text(encoding="utf-8").strip()
            except Exception:
                pass
        return "# Default Project Conventions: Follow PEP8 and test code."

    def update_tier2_state(self, goal: str, tasks: List[Dict[str, Any]], current_idx: int, message: str = ""):
        content = f"# Reactive Agent State\n\n**Goal**: {goal}\n**Status**: {message}\n\n## Subtasks:\n"
        for i, t in enumerate(tasks):
            char = "x" if i < current_idx else ("/" if i == current_idx else " ")
            content += f"- [{char}] Step {t.get('step_id', i+1)}: {t.get('description', '')}\n"
        
        try:
            self.state_md_path.write_text(content, encoding="utf-8")
        except Exception:
            pass

    def build_tier3_adaptive_reminders(self, last_failing_code: Optional[str] = None, last_error: Optional[str] = None) -> str:
        reminders = []
        if last_error:
            reminders.append(f"⚠️ [Last Error Traceback]: {last_error}")
        if last_failing_code:
            reminders.append("📄 [Previous Attempt]: Code failed verification. Ensure requirements are met.")
        return "\n".join(reminders)

    def log_tier4_dpo_pair(self, prompt: str, rejected: str, chosen: str, error: str):
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
# 4. UNIFIED TOOL STRATEGY PATTERN (With Crawl4AI Web Crawler)
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

class WebCrawlTool(BaseTool):
    name = "web_crawl"
    description = "Crawls a web page using Crawl4AI and converts it to clean, structured LLM-ready markdown."

    def __init__(self):
        self.crawler = WebScraperEngine()

    def execute(self, params: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        url = params["url"]
        return self.crawler.crawl_sync(url)

class ChromaMemoryTool(BaseTool):
    name = "chroma_search"
    description = "Searches codebase and documentation vectors using ChromaDB semantic similarity."

    def __init__(self):
        from chroma_store import ChromaVectorMemory
        self.chroma = ChromaVectorMemory()

    def execute(self, params: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        query = params.get("query", "")
        n_results = params.get("n_results", 3)
        hits = self.chroma.semantic_search(query, n_results=n_results)
        return {
            "status": "SUCCESS",
            "query": query,
            "hits_count": len(hits),
            "hits": hits
        }

# ============================================================================
# 5. THE ASYNC GENERATOR AGENT LOOP ENGINE
# ============================================================================

class AgentHarnessV2:
    def __init__(self, workspace_dir: str = "/Users/adarrsh/workspace", default_model: str = "ling-3.0-flash"):
        self.workspace_dir = Path(workspace_dir)
        self.memory = MemoryManager(self.workspace_dir)
        self.models = ModelRegistry(default_model)
        self.tools: Dict[str, BaseTool] = {
            "file_write": FileWriteTool(),
            "ast_validate": ASTValidatorTool(),
            "shell_exec": ShellExecTool(),
            "web_crawl": WebCrawlTool(),
            "chroma_search": ChromaMemoryTool()
        }

    def set_model(self, model_key: str):
        return self.models.switch_model(model_key)

    def run_agent_loop(self, goal: str, tasks: List[Dict[str, Any]], max_turns_per_task: int = 3) -> Generator[AgentEvent, None, TerminalResult]:
        start_time = time.time()
        event_count = 0
        profile = self.models.get_active_profile()

        conventions = self.memory.load_tier1_conventions()
        yield AgentEvent("SESSION_START", {
            "goal": goal,
            "model": profile.display_name,
            "model_id": profile.model_id,
            "architecture": profile.architecture,
            "ttft_ms": profile.simulated_ttft_ms,
            "speed_tokens_sec": profile.simulated_tokens_sec,
            "conventions_loaded": bool(conventions),
            "num_tasks": len(tasks)
        })
        event_count += 1

        for idx, task in enumerate(tasks):
            desc = task.get("description", "")
            target_file = task.get("target_file", "output.py")
            crawl_url = task.get("crawl_url")
            test_cmd = task.get("test_cmd", f"{sys.executable} -m py_compile {target_file}")
            
            self.memory.update_tier2_state(goal, tasks, idx, f"Working on Step {idx+1}")
            
            # If task includes web crawling (Crawl4AI)
            if crawl_url:
                yield AgentEvent("TOOL_START", {"tool": "web_crawl", "url": crawl_url})
                event_count += 1
                crawl_res = self.tools["web_crawl"].execute({"url": crawl_url}, {"workspace_dir": self.workspace_dir})
                yield AgentEvent("TOOL_END", {"tool": "web_crawl", "status": crawl_res["status"], "title": crawl_res.get("title")})
                event_count += 1

            turn = 0
            last_code = None
            last_error = None
            task_success = False

            while turn < max_turns_per_task and not task_success:
                turn += 1
                reminders = self.memory.build_tier3_adaptive_reminders(last_code, last_error)
                
                yield AgentEvent("TURN_START", {
                    "task_idx": idx,
                    "turn": turn,
                    "model": profile.model_id,
                    "target_file": target_file,
                    "has_reminders": bool(reminders)
                })
                event_count += 1

                candidate_code = f"# Model: {profile.model_id}\n# Auto-generated code for: {desc}\nimport os\n\ndef run():\n    return '{desc}'\n"
                
                yield AgentEvent("TOOL_START", {"tool": "ast_validate", "file": target_file})
                event_count += 1
                ast_res = self.tools["ast_validate"].execute({"code": candidate_code}, {"workspace_dir": self.workspace_dir})
                
                if ast_res["status"] != "PASSED":
                    last_error = ast_res["error"]
                    last_code = candidate_code
                    yield AgentEvent("EVAL_FAIL", {"reason": "AST_SYNTAX_ERROR", "error": last_error})
                    event_count += 1
                    continue

                yield AgentEvent("TOOL_START", {"tool": "file_write", "file": target_file})
                event_count += 1
                self.tools["file_write"].execute({"target_file": target_file, "content": candidate_code}, {"workspace_dir": self.workspace_dir})

                yield AgentEvent("TOOL_START", {"tool": "shell_exec", "command": test_cmd})
                event_count += 1
                shell_res = self.tools["shell_exec"].execute({"command": test_cmd}, {"workspace_dir": self.workspace_dir})

                if shell_res["status"] == "PASSED":
                    task_success = True
                    yield AgentEvent("EVAL_PASS", {"step_id": task.get("step_id", idx+1), "file": target_file, "latency_ms": profile.simulated_ttft_ms})
                    event_count += 1
                    
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
                return TerminalResult(
                    status="ERROR",
                    summary=f"Task {idx+1} failed after {max_turns_per_task} turns.",
                    total_turns=idx+1,
                    total_duration_sec=time.time() - start_time,
                    events_logged=event_count,
                    active_model=profile.model_id,
                    avg_ttft_ms=profile.simulated_ttft_ms,
                    avg_tokens_per_sec=profile.simulated_tokens_sec
                )

        self.memory.update_tier2_state(goal, tasks, len(tasks), "ALL TASKS COMPLETED")
        return TerminalResult(
            status="COMPLETE",
            summary="Goal achieved successfully with active model.",
            total_turns=len(tasks),
            total_duration_sec=time.time() - start_time,
            events_logged=event_count,
            active_model=profile.model_id,
            avg_ttft_ms=profile.simulated_ttft_ms,
            avg_tokens_per_sec=profile.simulated_tokens_sec
        )

if __name__ == "__main__":
    h = AgentHarnessV2()
    test_tasks = [
        {"step_id": 1, "description": "Crawl Chainlit Docs and extract overview", "crawl_url": "https://docs.chainlit.io/get-started/overview", "target_file": "docs_mod.py"}
    ]
    runner = h.run_agent_loop("Test Web Crawling with Crawl4AI", test_tasks)
    try:
        while True:
            ev = next(runner)
            print(f"📡 [{ev.event_type}] {json.dumps(ev.payload)}")
    except StopIteration as e:
        res = e.value
        print(f"\n🎉 [Result]: {res.status} | Events: {res.events_logged} | Duration: {res.total_duration_sec:.2f}s")
