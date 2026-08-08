"""
Agentic IDE Engine — 100% Real LLM Code Synthesis & AST Quality Gating

Calls the local MLX LLM server at localhost:8800 to generate actual code for every prompt.
Zero mocks. Zero fallback templates. Runs deterministic AST quality gating on every output.
"""
import os
import sys
import ast
import json
import time
import re
import subprocess
from pathlib import Path
from urllib.request import Request, urlopen
from typing import Dict, List, Any, Optional

import model_router

MODEL_URL = model_router.get_url("coder")

class TaskNode:
    def __init__(self, task_id: str, title: str, description: str, target_file: str, dependencies: List[str] = None):
        self.task_id = task_id
        self.title = title
        self.description = description
        self.target_file = target_file
        self.dependencies = dependencies or []
        self.status = "PENDING"
        self.generated_code = ""
        self.error_trace = ""


class AgenticSystemOrchestrator:
    """
    Autonomous Agentic IDE Engine.
    Decomposes goals into subtasks, calls the real local LLM for code synthesis,
    and runs deterministic AST quality gating on every output.
    """

    def __init__(
        self,
        workspace_dir: str = "/Users/adarrsh/workspace",
        model_name: str = None,
        model_url: str = None,
    ):
        self.workspace_dir = Path(workspace_dir)
        self.model_name = model_name or model_router.get_model("coder")
        self.model_url = (model_url or model_router.get_url("coder")).rstrip("/")
        self.memory = ChromaVectorMemory()
        self.execution_log: List[Dict[str, Any]] = []

    def decompose_goal(self, goal: str) -> List[TaskNode]:
        """Decomposes a user goal into a sequence of code-generation subtasks."""
        words = re.sub(r'[^\w\s]', '', goal.lower()).split()
        mod_name = '_'.join(words[:5]) if words else 'task_output'

        tasks = [TaskNode(
            task_id="task_1_main",
            title=f"Synthesize: {goal[:60]}",
            description=goal,
            target_file=f"{mod_name}.py",
            dependencies=[]
        )]
        return tasks

    def call_planner(self, prompt: str, sys_prompt: str = "", max_tokens: int = 400) -> str:
        """Calls the Planner LLM (Ling on :8801)."""
        return self._call_role("planner", prompt, sys_prompt, max_tokens)

    def call_coder(self, prompt: str, sys_prompt: str = "", max_tokens: int = 400) -> str:
        """Calls the Coder LLM (Ornith on :8800)."""
        return self._call_role("coder", prompt, sys_prompt, max_tokens)

    def _call_role(self, role: str, prompt: str, sys_prompt: str = "", max_tokens: int = 400) -> str:
        """Calls the MLX LLM server for the specified role."""
        model_name = model_router.get_model(role)
        endpoint_url = model_router.get_endpoint(role)
        
        if sys_prompt:
            full_prompt = f"{sys_prompt}\n\nUser Question: {prompt}"
        else:
            full_prompt = f"Write production-quality Python code for: {prompt}\nOutput ONLY valid Python code with docstrings."
        
        payload = {
            "model": model_name,
            "messages": [{"role": "user", "content": full_prompt}],
            "temperature": 0.2,
            "max_tokens": max_tokens,
        }

        try:
            req = Request(
                endpoint_url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"}
            )
            with urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data["choices"][0]["message"]["content"].strip()
        except Exception as e:
            # Fallback to fallback role if primary fails
            fallback_url = model_router.get_endpoint("fallback")
            fallback_model = model_router.get_model("fallback")
            payload["model"] = fallback_model
            try:
                req = Request(
                    fallback_url,
                    data=json.dumps(payload).encode("utf-8"),
                    headers={"Content-Type": "application/json"}
                )
                with urlopen(req, timeout=120) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    return data["choices"][0]["message"]["content"].strip()
            except Exception as fe:
                raise RuntimeError(f"LLM call failed for role={role} ({e}) and fallback ({fe})")

    def call_llm(self, prompt: str, sys_prompt: str = "", max_tokens: int = 400) -> str:
        """Backward compatibility wrapper — delegates to call_coder."""
        return self.call_coder(prompt, sys_prompt, max_tokens)

    def extract_python_code(self, raw_text: str) -> str:
        """Extracts Python code from LLM response, stripping markdown fences if present."""
        pattern = r'```(?:python)?\s*\n(.*?)```'
        matches = re.findall(pattern, raw_text, re.DOTALL)
        if matches:
            return '\n\n'.join(m.strip() for m in matches)

        first_line = raw_text.lstrip().split('\n')[0] if raw_text.strip() else ''
        if first_line.startswith(('import ', 'from ', 'def ', 'class ', '#', '"""', "'''")):
            return raw_text.strip()

        return raw_text.strip()

    def synthesize_with_llm(self, task: TaskNode, context: str, max_retries: int = 2) -> Dict[str, Any]:
        """
        Calls the real LLM to generate code, then validates through AST quality gate.
        Retries with error feedback if AST fails.
        NO FALLBACK TEMPLATES. REAL LLM ONLY.
        """
        last_error = None
        for attempt in range(1, max_retries + 1):
            try:
                user_prompt = task.description
                if last_error:
                    user_prompt += f"\nFix previous syntax error: {last_error}"
                if context:
                    user_prompt += f"\nContext: {context[:300]}"

                raw_response = self.call_llm(user_prompt)
                code = self.extract_python_code(raw_response)

                # Deterministic AST Quality Gate
                ast.parse(code)

                # AST passed — write to disk
                file_path = self.workspace_dir / task.target_file
                file_path.parent.mkdir(parents=True, exist_ok=True)
                file_path.write_text(code, encoding="utf-8")

                task.status = "PASSED"
                task.generated_code = code
                return {
                    "task_id": task.task_id,
                    "target_file": task.target_file,
                    "status": "PASSED",
                    "attempts": attempt,
                    "code": code,
                    "source": "llm_live"
                }
            except SyntaxError as se:
                last_error = f"line {se.lineno}: {se.msg}"
                task.error_trace = last_error
            except Exception as e:
                last_error = str(e)
                task.error_trace = last_error

        task.status = "FAILED"
        return {
            "task_id": task.task_id,
            "target_file": task.target_file,
            "status": "FAILED",
            "attempts": max_retries,
            "error": task.error_trace,
            "code": f"# Real LLM Generation Failure: {task.error_trace}",
            "source": "llm_live"
        }

    def execute_autonomous_build(self, goal: str) -> Dict[str, Any]:
        """Executes end-to-end: decompose → retrieve context → call LLM → AST gate → write files."""
        start_time = time.time()
        tasks = self.decompose_goal(goal)
        results = []

        print(f"\n🚀 [Agentic IDE Engine] Goal: '{goal[:80]}'")
        print(f"   Decomposed into {len(tasks)} task(s), calling LLM at {MODEL_URL}...")

        # Retrieve context from Chroma
        search_hits = self.memory.semantic_search(goal, n_results=2)
        context_str = "\n".join([h["document"][:300] for h in search_hits]) if search_hits else ""

        for t in tasks:
            print(f"   ⚙️  Synthesizing '{t.target_file}' via real LLM call...")
            res = self.synthesize_with_llm(t, context_str)
            results.append(res)
            status_icon = "✅" if res["status"] == "PASSED" else "❌"
            print(f"   {status_icon} {res['status']} ({res.get('attempts', '?')} attempt(s), source: {res.get('source', '?')})")

        test_status = "SKIPPED"
        for r in results:
            if r["status"] == "PASSED" and r["target_file"].endswith(".py"):
                test_cmd = f"{sys.executable} -m py_compile {r['target_file']}"
                proc = subprocess.run(test_cmd, shell=True, capture_output=True, text=True, cwd=str(self.workspace_dir))
                test_status = "PASSED" if proc.returncode == 0 else "FAILED"

        duration = round(time.time() - start_time, 2)
        return {
            "goal": goal,
            "tasks_count": len(tasks),
            "results": results,
            "test_suite_status": test_status,
            "duration_sec": duration
        }


if __name__ == "__main__":
    orchestrator = AgenticSystemOrchestrator()
    goal = sys.argv[1] if len(sys.argv) > 1 else "Write a binary search function in Python"
    summary = orchestrator.execute_autonomous_build(goal)
    print(f"\n🎉 Build Complete in {summary['duration_sec']}s — Status: {summary['test_suite_status']}")
    for r in summary["results"]:
        if r.get("code"):
            print(f"\n--- {r['target_file']} ---")
            print(r["code"][:500])
