import unittest
import os
import tempfile
import threading
import p2_worker_stub as p2

class TestCheckpoint(unittest.TestCase):
    def setUp(self):
        self.temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".json")
        self.temp_file.close()
        self.original_ckpt = p2.CHECKPOINT_FILE
        p2.CHECKPOINT_FILE = self.temp_file.name

    def tearDown(self):
        p2.CHECKPOINT_FILE = self.original_ckpt
        if os.path.exists(self.temp_file.name):
            os.remove(self.temp_file.name)
        lock_file = self.temp_file.name + ".lock"
        if os.path.exists(lock_file):
            os.remove(lock_file)

    def test_save_and_load_roundtrip(self):
        token = "token-123"
        p2.save_checkpoint(token, "task-1", "Step 2/5", {"key": "val"})
        state = p2.load_checkpoint(token)
        self.assertEqual(state["task_id"], "task-1")
        self.assertEqual(state["progress"], "Step 2/5")
        self.assertEqual(state["metadata"]["key"], "val")

    def test_save_creates_file(self):
        p2.save_checkpoint("t-1", "task-x", "Step 1")
        self.assertTrue(os.path.exists(p2.CHECKPOINT_FILE))

    def test_load_missing_token_returns_empty(self):
        state = p2.load_checkpoint("nonexistent-token")
        self.assertTrue(state == {} or state is None)

    def test_concurrent_saves_no_corruption(self):
        threads = []
        for i in range(10):
            t = threading.Thread(target=p2.save_checkpoint, args=(f"tok-{i}", f"task-{i}", f"Step {i}"))
            threads.append(t)
            t.start()
        for t in threads:
            t.join()
        
        data = p2._read_checkpoints()
        self.assertEqual(len(data), 10)

    def test_multiple_checkpoints_coexist(self):
        p2.save_checkpoint("c1", "t1", "p1")
        p2.save_checkpoint("c2", "t2", "p2")
        self.assertEqual(p2.load_checkpoint("c1")["task_id"], "t1")
        self.assertEqual(p2.load_checkpoint("c2")["task_id"], "t2")

if __name__ == "__main__":
    unittest.main()
