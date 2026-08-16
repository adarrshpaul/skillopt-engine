import unittest
import tempfile
from pathlib import Path
from core.compaction import (
    save_wip_state,
    restore_wip_state,
    clear_wip_state,
    CompactionGovernor,
    WIPState,
    estimate_tokens
)
from core.session_ledger import JSONLSessionLedger, SessionEvent

class TestCompaction(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp_dir.name)
        self.wip_path = self.tmp_path / ".test_wip.json"
        self.dpo_path = self.tmp_path / "test_dpo.jsonl"
        self.gov = CompactionGovernor(
            token_limit=1000,
            trigger_ratio=0.8,
            keep_recent_tools=2,
            wip_file=str(self.wip_path),
            dpo_log_path=str(self.dpo_path)
        )

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_estimate_tokens(self):
        self.assertEqual(estimate_tokens("12345678"), 2)
        msgs = [{"role": "user", "content": "hello world"}, {"role": "assistant", "content": "test response"}]
        self.assertGreater(estimate_tokens(msgs), 5)

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
        self.assertFalse(self.gov.should_compact(500))
        self.assertTrue(self.gov.should_compact(850))

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

    def test_tier1_clear_tool_uses(self):
        ledger_file = self.tmp_path / "test_ledger.jsonl"
        ledger = JSONLSessionLedger(path=str(ledger_file), session_id="test-sess")

        # Add 4 tool results with large outputs
        for i in range(1, 5):
            ledger.append(SessionEvent(
                event_type="tool/result",
                payload={"call": f"read_file('file_{i}.py')", "output": "x" * 300}
            ))

        # Run Tier 1 clear_tool_uses (keep_recent_tools=2)
        evicted = self.gov.tier1_clear_tool_uses(ledger, turn_start_seq=0)
        self.assertEqual(evicted, 2)

        # Check ledger events
        events = list(ledger.replay(0))
        evict_events = [e for e in events if e.event_type == "compaction/evict_tools"]
        self.assertEqual(len(evict_events), 1)
        self.assertEqual(evict_events[0].payload.get("evicted_seqs"), [1, 2])

        # Verify DPO archive was written
        self.assertTrue(self.dpo_path.exists())
        lines = self.dpo_path.read_text().strip().split("\n")
        self.assertEqual(len(lines), 2)

    def test_build_tier2_summary_prompt(self):
        msgs = [
            {"role": "user", "content": "Create an API"},
            {"role": "assistant", "content": "I will write app.py"},
            {"role": "user", "content": "You called write_file, success"}
        ]
        prompt = self.gov.build_tier2_summary_prompt(msgs)
        self.assertIn("### 1. Task Overview", prompt)
        self.assertIn("### 2. Current State", prompt)
        self.assertIn("### 3. Important Discoveries", prompt)
        self.assertIn("### 4. Next Steps", prompt)
        self.assertIn("### 5. Context to Preserve", prompt)

if __name__ == "__main__":
    unittest.main()
