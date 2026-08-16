import unittest
import tempfile
import os
from pathlib import Path
from core.session_ledger import SessionEvent, JSONLSessionLedger, SQLiteSessionLedger
from contracts import SessionLedger

class TestSessionLedger(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp_dir.name)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_jsonl_ledger_append_and_replay(self):
        log_file = self.tmp_path / "test_session.jsonl"
        ledger = JSONLSessionLedger(log_file, session_id="sess-001")
        
        # Verify Protocol adherence
        self.assertIsInstance(ledger, SessionLedger)

        seq1 = ledger.append(SessionEvent(event_type="turn/start", payload={"goal": "build feature"}))
        seq2 = ledger.append(SessionEvent(event_type="tool/call", payload={"tool": "bash", "cmd": "ls"}, tokens_in=50, tokens_out=10))
        seq3 = ledger.append(SessionEvent(event_type="tool/result", payload={"output": "file1\nfile2"}))

        self.assertEqual(seq1, 1)
        self.assertEqual(seq2, 2)
        self.assertEqual(seq3, 3)

        events = ledger.replay(0)
        self.assertEqual(len(events), 3)
        self.assertEqual(events[0].event_type, "turn/start")
        self.assertEqual(events[1].payload["tool"], "bash")
        self.assertEqual(events[1].tokens_in, 50)

        # Replay from sequence 2
        events_from_2 = ledger.replay(2)
        self.assertEqual(len(events_from_2), 2)
        self.assertEqual(events_from_2[0].seq, 2)

        # Token usage
        tokens = ledger.get_token_usage()
        self.assertEqual(tokens["total_tokens_in"], 50)
        self.assertEqual(tokens["total_tokens_out"], 10)
        self.assertEqual(tokens["total_tokens"], 60)

    def test_jsonl_ledger_fork(self):
        log_file = self.tmp_path / "session_parent.jsonl"
        ledger = JSONLSessionLedger(log_file, session_id="parent")
        ledger.append(SessionEvent(event_type="turn/start"))
        ledger.append(SessionEvent(event_type="tool/call", payload={"cmd": "step 1"}))
        ledger.append(SessionEvent(event_type="tool/call", payload={"cmd": "step 2"}))

        forked = ledger.fork(boundary_seq=2)
        forked_events = forked.replay(0)
        self.assertEqual(len(forked_events), 2)
        self.assertEqual(forked_events[1].payload["cmd"], "step 1")

    def test_sqlite_ledger_append_and_replay(self):
        db_file = self.tmp_path / "session.db"
        ledger = SQLiteSessionLedger(db_file, session_id="sess-sql")
        
        self.assertIsInstance(ledger, SessionLedger)

        seq1 = ledger.append(SessionEvent(event_type="turn/start", payload={"task": "init"}))
        seq2 = ledger.append(SessionEvent(event_type="tool/call", payload={"tool": "write_file"}, tokens_in=100))

        self.assertEqual(seq1, 1)
        self.assertEqual(seq2, 2)

        events = ledger.replay(0)
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0].payload["task"], "init")

if __name__ == "__main__":
    unittest.main()
