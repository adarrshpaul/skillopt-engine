import unittest
import os
import tempfile
import sqlite3
import p3_faiss_worker as p3

class TestFaissWorker(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.original_db = p3.DB_FILE
        self.original_idx = p3.INDEX_FILE
        p3.DB_FILE = os.path.join(self.tmp_dir.name, "test_p3.db")
        p3.INDEX_FILE = os.path.join(self.tmp_dir.name, "test_faiss.bin")
        self.worker = p3.P3Worker()

    def tearDown(self):
        p3.DB_FILE = self.original_db
        p3.INDEX_FILE = self.original_idx
        self.tmp_dir.cleanup()

    def test_add_documents_creates_index(self):
        docs = [{"text": "FAISS is a vector search library.", "metadata": {"tag": "ml"}}]
        self.worker.add_documents(docs)
        self.assertTrue(os.path.exists(p3.INDEX_FILE))

    def test_query_returns_results(self):
        docs = [
            {"text": "Python is a programming language.", "metadata": {"lang": "py"}},
            {"text": "Cooking pasta requires boiling water.", "metadata": {"food": "pasta"}}
        ]
        self.worker.add_documents(docs)
        res = self.worker.query("code in python", top_k=1)
        self.assertEqual(len(res), 1)
        self.assertIn("Python", res[0]["text"])

    def test_query_result_has_score(self):
        docs = [{"text": "Neural networks learn representations."}]
        self.worker.add_documents(docs)
        res = self.worker.query("machine learning", top_k=1)
        self.assertIn("score", res[0])
        self.assertIsInstance(res[0]["score"], float)

    def test_empty_docs_no_crash(self):
        self.worker.add_documents([])

    def test_metadata_json_roundtrip(self):
        docs = [{"text": "Document with rich metadata", "metadata": {"author": "Alice", "version": 2}}]
        self.worker.add_documents(docs)
        res = self.worker.query("Document", top_k=1)
        self.assertEqual(res[0]["metadata"]["author"], "Alice")
        self.assertEqual(res[0]["metadata"]["version"], 2)

    def test_sqlite_index_exists(self):
        cur = self.worker.conn.cursor()
        cur.execute("PRAGMA index_list('docs')")
        indices = [row[1] for row in cur.fetchall()]
        self.assertIn("idx_faiss_id", indices)

if __name__ == "__main__":
    unittest.main()
