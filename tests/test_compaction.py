import unittest
import tempfile
from pathlib import Path
from core.compaction import save_wip_state, restore_wip_state, clear_wip_state, CompactionGovernor, WIPState

class TestCompaction(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp_dir.name)
        self.wip_path = self.tmp_path / ".test_wip.json"
        self.gov = CompactionGovernor(token_limit=10000, trigger_ratio=0.8, wip_file=str(self.wip_path))

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_save_and_restore_wip_state(self):
        tasks = [{"task_id": "T01", "description": "task 1"}, {"task_id": "T02", "description": "task 2"}]
        save_wip_state(
            session_id="sess-comp-1",
            current_task_idx=1,
            active_task_id="T02",
            tasks=tasks,
            active_diffs="diff --git a/app.py b/app.py",
            ledger_seq=42,
            path=self.wip_path
        )

        self.assertTrue(self.wip_path.exists())
        state = restore_wip_state(self.wip_path)
        self.assertIsNotNone(state)
        self.assertEqual(state.session_id, "sess-comp-1")
        self.assertEqual(state.current_task_idx, 1)
        self.assertEqual(state.active_task_id, "T02")
        self.assertEqual(state.ledger_seq, 42)
        self.assertEqual(len(state.tasks), 2)

        # Clear state
        clear_wip_state(self.wip_path)
        self.assertFalse(self.wip_path.exists())
        self.assertIsNone(restore_wip_state(self.wip_path))

    def test_compaction_governor_threshold_and_reinject(self):
        self.assertFalse(self.gov.should_compact(5000))
        self.assertTrue(self.gov.should_compact(8500))

        # Pre-compact save
        state = self.gov.pre_compact(
            session_id="sess-02",
            current_idx=0,
            active_task_id="T01",
            tasks=[{"task_id": "T01"}],
            active_diffs="modified config.py",
            ledger_seq=10
        )
        self.assertEqual(state.active_task_id, "T01")

        # Post-compact context generation
        context_str = self.gov.build_post_compact_context(state)
        self.assertIn("CONTEXT COMPACTION OCCURRED", context_str)
        self.assertIn("Task ID: T01", context_str)
        self.assertIn("seq #10", context_str)

if __name__ == "__main__":
    unittest.main()
