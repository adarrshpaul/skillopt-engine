import unittest
import tempfile
from pathlib import Path
from core.task_ledger import MarkdownTaskLedger, TaskSpec
from contracts import TaskLedger, TaskSpecData

class TestTaskLedger(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp_dir.name)
        self.plans_file = self.tmp_path / "Plans.md"
        self.ledger = MarkdownTaskLedger(self.plans_file)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_protocol_conformance(self):
        self.assertIsInstance(self.ledger, TaskLedger)

    def test_add_and_update_task(self):
        task = TaskSpec(
            task_id="T01",
            description="Create authentication endpoint",
            target_files=["auth.py", "test_auth.py"],
            dependencies=[],
            test_cmd="pytest tests/test_auth.py",
            status="pending"
        )
        tid = self.ledger.add_task(task)
        self.assertEqual(tid, "T01")

        # Check Plans.md was written
        self.assertTrue(self.plans_file.exists())
        content = self.plans_file.read_text()
        self.assertIn("[ ]", content)
        self.assertIn("T01", content)
        self.assertIn("Create authentication endpoint", content)

        # Update status to done
        self.ledger.update_status("T01", "done")
        content_after = self.plans_file.read_text()
        self.assertIn("[x]", content_after)

    def test_reload_from_file(self):
        self.ledger.add_task(TaskSpec(
            task_id="T02",
            description="Add rate limiter",
            target_files=["limiter.py"],
            status="in_progress"
        ))

        # Create new ledger instance pointing to same file
        reloaded_ledger = MarkdownTaskLedger(self.plans_file)
        t = reloaded_ledger.get_task("T02")
        self.assertIsNotNone(t)
        self.assertEqual(t.description, "Add rate limiter")
        self.assertEqual(t.status, "in_progress")

    def test_phantom_task_drift_detection(self):
        # Marked done but target file does not exist
        self.ledger.add_task(TaskSpec(
            task_id="T03",
            description="Write non-existent module",
            target_files=["non_existent_module.py"],
            status="done"
        ))

        drift = self.ledger.get_drift(root_dir=self.tmp_path)
        self.assertEqual(len(drift), 1)
        self.assertEqual(drift[0].task_id, "T03")
        self.assertEqual(drift[0].drift_type, "phantom_completion")

if __name__ == "__main__":
    unittest.main()
