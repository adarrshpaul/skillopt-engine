import unittest
import os
import tempfile
import sys
sys.path.insert(0, '/Users/adarrsh/workspace')
import p3_faiss_worker as p3

class TestIntegrationFaissGraph(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.original_db = p3.DB_FILE
        self.original_idx = p3.INDEX_FILE
        p3.DB_FILE = os.path.join(self.tmp_dir.name, "e2e_p3.db")
        p3.INDEX_FILE = os.path.join(self.tmp_dir.name, "e2e_faiss.bin")
        self.worker = p3.P3Worker()

    def tearDown(self):
        p3.DB_FILE = self.original_db
        p3.INDEX_FILE = self.original_idx
        self.tmp_dir.cleanup()

    def test_e2e_faiss_ingest_and_query(self):
        docs = [
            {"id": "doc-1", "text": "Python is an interpreted programming language.", "metadata": {"lang": "py"}},
            {"id": "doc-2", "text": "JavaScript is a language for web development.", "metadata": {"lang": "js"}},
            {"id": "doc-3", "text": "Rust provides memory safety without garbage collection.", "metadata": {"lang": "rs"}}
        ]
        self.worker.add_documents(docs)
        results = self.worker.query("memory safety language", top_k=1)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["id"], "doc-3")
        self.assertIn("score", results[0])

    def test_e2e_faiss_query_returns_relevant(self):
        docs = [
            {"id": "doc-py", "text": "Python machine learning models and transformers.", "metadata": {"tag": "ai"}},
            {"id": "doc-food", "text": "Baking bread requires flour, water, and yeast.", "metadata": {"tag": "food"}}
        ]
        self.worker.add_documents(docs)
        results = self.worker.query("artificial intelligence model", top_k=1)
        self.assertEqual(results[0]["id"], "doc-py")

if __name__ == "__main__":
    unittest.main()
