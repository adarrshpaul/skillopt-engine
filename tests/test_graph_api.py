import unittest
import os
import tempfile
import sys
sys.path.insert(0, '/Users/adarrsh/workspace')
from fastapi.testclient import TestClient
import graph_store
from graph_api_server import app

class TestGraphAPI(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.original_db = graph_store.DB_FILE
        graph_store.DB_FILE = os.path.join(self.tmp_dir.name, "test_api_graph.db")
        graph_store.init_db()
        self.client = TestClient(app)

    def tearDown(self):
        graph_store.DB_FILE = self.original_db
        self.tmp_dir.cleanup()

    def test_chat_creates_nodes(self):
        res = self.client.post("/api/chat", json={"text": "Hello world", "priority": 1})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("node_id", data)
        self.assertIn("action", data)

    def test_chat_returns_action(self):
        res = self.client.post("/api/chat", json={"text": "Test query", "priority": 1})
        data = res.json()
        self.assertIn("action", data)
        self.assertIn("reason", data)

    def test_get_graph_returns_structure(self):
        self.client.post("/api/chat", json={"text": "Sample prompt"})
        res = self.client.get("/api/graph")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("nodes", data)
        self.assertIn("edges", data)
        self.assertTrue(len(data["nodes"]) >= 2)

    def test_resume_returns_status(self):
        res = self.client.post("/api/resume", json={"checkpoint_token": "nonexistent-token"})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("status", data)

    def test_chat_graceful_fallback(self):
        # Even when gRPC is down, API returns 200 with action="error" and fallback response
        res = self.client.post("/api/chat", json={"text": "Fallback test"})
        self.assertEqual(res.status_code, 200)

if __name__ == "__main__":
    unittest.main()
