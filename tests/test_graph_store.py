import unittest
import sqlite3
import graph_store

import tempfile
import os

class TestGraphStore(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.original_db = graph_store.DB_FILE
        graph_store.DB_FILE = os.path.join(self.tmp_dir.name, "test_graph.db")
        graph_store.init_db()

    def tearDown(self):
        graph_store.DB_FILE = self.original_db
        self.tmp_dir.cleanup()

    def test_init_creates_tables(self):
        conn = graph_store.get_db()
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [r[0] for r in cur.fetchall()]
        conn.close()
        self.assertIn("nodes", tables)
        self.assertIn("edges", tables)

    def test_add_node_persists(self):
        graph_store.add_node("node-1", "prompt", "Hello World", model="ornith-9b")
        graph = graph_store.get_graph()
        self.assertEqual(len(graph["nodes"]), 1)
        self.assertEqual(graph["nodes"][0]["id"], "node-1")
        self.assertEqual(graph["nodes"][0]["content"], "Hello World")
        self.assertEqual(graph["nodes"][0]["model"], "ornith-9b")

    def test_add_edge_persists(self):
        graph_store.add_node("n1", "prompt", "P")
        graph_store.add_node("n2", "response", "R")
        graph_store.add_edge("n1", "n2", "generates")
        graph = graph_store.get_graph()
        self.assertEqual(len(graph["edges"]), 1)
        self.assertEqual(graph["edges"][0]["src"], "n1")
        self.assertEqual(graph["edges"][0]["dst"], "n2")
        self.assertEqual(graph["edges"][0]["label"], "generates")

    def test_duplicate_node_upserts(self):
        graph_store.add_node("n1", "prompt", "First")
        graph_store.add_node("n1", "prompt", "Second")
        graph = graph_store.get_graph()
        self.assertEqual(len(graph["nodes"]), 1)
        self.assertEqual(graph["nodes"][0]["content"], "Second")

    def test_get_graph_empty(self):
        graph = graph_store.get_graph()
        self.assertEqual(graph["nodes"], [])
        self.assertEqual(graph["edges"], [])

    def test_metadata_json_roundtrip(self):
        graph_store.add_node("n1", "task", "Do X", metadata={"key": "value", "count": 42})
        graph = graph_store.get_graph()
        node = graph["nodes"][0]
        self.assertEqual(node["metadata"]["key"], "value")
        self.assertEqual(node["metadata"]["count"], 42)

if __name__ == "__main__":
    unittest.main()
