import unittest
import tempfile
from pathlib import Path
from core.parallel_executor import WorktreeExecutor, ExecutionResult

class TestParallelExecutor(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp_dir.name)
        self.executor = WorktreeExecutor(repo_root=self.tmp_path, max_workers=2, use_git_worktree=False)

    def tearDown(self):
        self.executor.cleanup_all()
        self.tmp_dir.cleanup()

    def test_parallel_execution_independent_tasks(self):
        tasks = [
            {"task_id": "T01", "description": "Write module A", "dependencies": []},
            {"task_id": "T02", "description": "Write module B", "dependencies": []},
        ]

        def sample_worker(task, workspace_path):
            test_file = workspace_path / f"{task['task_id']}.txt"
            test_file.write_text("done")
            return f"Processed {task['task_id']} in {workspace_path.name}"

        results = self.executor.execute_parallel(tasks, sample_worker)
        self.assertEqual(len(results), 2)
        successes = [r for r in results if r.status == "success"]
        self.assertEqual(len(successes), 2)

    def test_parallel_execution_with_dependency_ordering(self):
        tasks = [
            {"task_id": "T01", "description": "Base setup", "dependencies": []},
            {"task_id": "T02", "description": "Dependent task", "dependencies": ["T01"]},
        ]
        execution_order = []

        def tracking_worker(task, workspace_path):
            execution_order.append(task["task_id"])
            return "ok"

        results = self.executor.execute_parallel(tasks, tracking_worker)
        self.assertEqual(len(results), 2)
        self.assertEqual(execution_order, ["T01", "T02"])

if __name__ == "__main__":
    unittest.main()
