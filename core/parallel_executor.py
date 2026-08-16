"""
Parallel task executor with Git worktree and directory isolation.
Inspired by Claude Code Harness's Breezing orchestrator and DeepSeek's subagent workers.
Enables concurrent execution of independent task graph branches with zero filesystem collision.
"""
import os
import shutil
import subprocess
import tempfile
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Callable, Any, Optional, Union
from core.task_ledger import TaskSpec

@dataclass
class ExecutionResult:
    task_id: str
    status: str           # "success", "failure", "skipped"
    output: str = ""
    error: str = ""
    duration_ms: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


class WorktreeExecutor:
    """
    Executes independent tasks concurrently in isolated Git worktrees
    or isolated directory workspaces.
    """
    def __init__(self, repo_root: Union[str, Path] = ".", max_workers: int = 3, use_git_worktree: bool = True):
        self.repo_root = Path(repo_root).resolve()
        self.max_workers = max_workers
        self.use_git_worktree = use_git_worktree and (self.repo_root / ".git").exists()
        self._active_workspaces: List[Path] = []

    def _create_workspace(self, task_id: str) -> Path:
        clean_tid = task_id.replace("/", "_").replace(" ", "_")
        if self.use_git_worktree:
            branch = f"worktree/{clean_tid}_{uuid.uuid4().hex[:6]}"
            wt_path = self.repo_root / ".worktrees" / f"wt_{clean_tid}"
            wt_path.parent.mkdir(parents=True, exist_ok=True)
            # Remove any stale worktree at that path
            if wt_path.exists():
                subprocess.run(["git", "worktree", "remove", "--force", str(wt_path)],
                               cwd=self.repo_root, capture_output=True)
            cmd = ["git", "worktree", "add", "-b", branch, str(wt_path), "HEAD"]
            proc = subprocess.run(cmd, cwd=self.repo_root, capture_output=True, text=True)
            if proc.returncode == 0:
                self._active_workspaces.append(wt_path)
                return wt_path

        # Fallback: Isolated directory copy
        temp_dir = Path(tempfile.mkdtemp(prefix=f"workspace_task_{clean_tid}_"))
        self._active_workspaces.append(temp_dir)
        return temp_dir

    def _cleanup_workspace(self, ws_path: Path) -> None:
        try:
            if self.use_git_worktree and ".worktrees" in str(ws_path):
                subprocess.run(["git", "worktree", "remove", "--force", str(ws_path)],
                               cwd=self.repo_root, capture_output=True)
            elif ws_path.exists():
                shutil.rmtree(ws_path, ignore_errors=True)
        except Exception:
            pass

    def cleanup_all(self) -> None:
        for ws in list(self._active_workspaces):
            self._cleanup_workspace(ws)
        self._active_workspaces.clear()

    def execute_parallel(
        self,
        tasks: List[Union[TaskSpec, Dict[str, Any]]],
        worker_fn: Callable[[Dict[str, Any], Path], Any]
    ) -> List[ExecutionResult]:
        """
        Runs independent tasks concurrently in isolated worktrees.
        Tasks with unmet dependencies are deferred or scheduled after dependencies resolve.
        """
        results: List[ExecutionResult] = []
        completed_task_ids = set()
        task_dict: Dict[str, Dict[str, Any]] = {}

        # Normalize tasks to dicts
        for t in tasks:
            if hasattr(t, "to_dict"):
                d = t.to_dict()
            elif isinstance(t, dict):
                d = dict(t)
            else:
                d = {
                    "task_id": getattr(t, "task_id", str(uuid.uuid4().hex[:6])),
                    "description": getattr(t, "description", ""),
                    "dependencies": getattr(t, "dependencies", []),
                    "target_files": getattr(t, "target_files", [])
                }
            task_dict[d["task_id"]] = d

        pending_tasks = dict(task_dict)

        with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
            while pending_tasks:
                # Identify tasks whose dependencies are satisfied
                ready_tasks = [
                    t for t in pending_tasks.values()
                    if all(dep in completed_task_ids for dep in t.get("dependencies", []))
                ]

                if not ready_tasks:
                    # Circular or unsatisfied dependency
                    for t in pending_tasks.values():
                        results.append(ExecutionResult(
                            task_id=t["task_id"],
                            status="skipped",
                            error=f"Unmet dependencies: {t.get('dependencies', [])}"
                        ))
                    break

                # Dispatch ready tasks in parallel
                future_to_task = {}
                for t in ready_tasks:
                    tid = t["task_id"]
                    del pending_tasks[tid]
                    ws = self._create_workspace(tid)
                    future = pool.submit(self._run_single_worker, worker_fn, t, ws)
                    future_to_task[future] = (tid, ws)

                for future in as_completed(future_to_task):
                    tid, ws = future_to_task[future]
                    try:
                        res = future.result()
                        results.append(res)
                        if res.status == "success":
                            completed_task_ids.add(tid)
                    except Exception as e:
                        results.append(ExecutionResult(
                            task_id=tid,
                            status="failure",
                            error=str(e)
                        ))
                    finally:
                        self._cleanup_workspace(ws)

        return results

    def _run_single_worker(
        self,
        worker_fn: Callable[[Dict[str, Any], Path], Any],
        task: Dict[str, Any],
        workspace: Path
    ) -> ExecutionResult:
        import time
        start_t = time.time()
        tid = task["task_id"]
        try:
            out = worker_fn(task, workspace)
            duration = (time.time() - start_t) * 1000
            return ExecutionResult(
                task_id=tid,
                status="success",
                output=str(out),
                duration_ms=duration
            )
        except Exception as e:
            duration = (time.time() - start_t) * 1000
            return ExecutionResult(
                task_id=tid,
                status="failure",
                error=str(e),
                duration_ms=duration
            )
