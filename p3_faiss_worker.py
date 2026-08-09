import faiss
import sqlite3
import numpy as np
from sentence_transformers import SentenceTransformer
import os
import uuid
import json

DB_FILE = "p3_metadata.db"
INDEX_FILE = "faiss_index.bin"
EMBED_MODEL = "all-MiniLM-L6-v2"  # small embedder

class P3Worker:
    def __init__(self, dim=384):
        self.dim = dim
        self.model = SentenceTransformer(EMBED_MODEL, device="cpu")
        self._ensure_db()
        if os.path.exists(INDEX_FILE):
            self.index = faiss.read_index(INDEX_FILE)
        else:
            base_index = faiss.IndexFlatL2(self.dim)
            self.index = faiss.IndexIDMap(base_index)

    def _ensure_db(self):
        self.conn = sqlite3.connect(DB_FILE, check_same_thread=False)
        cur = self.conn.cursor()
        cur.execute("""
        CREATE TABLE IF NOT EXISTS docs (
            id TEXT PRIMARY KEY,
            text TEXT,
            metadata TEXT,
            faiss_id INTEGER
        )""")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_faiss_id ON docs (faiss_id)")
        self.conn.commit()

    def add_documents(self, docs):
        if not docs:
            return
            
        texts = [d["text"] for d in docs]
        ids = [d.get("id", str(uuid.uuid4())) for d in docs]
        embs = self.model.encode(texts, convert_to_numpy=True)
        faiss.normalize_L2(embs)
        
        # Generate integer IDs for IndexIDMap
        cur = self.conn.cursor()
        cur.execute("SELECT IFNULL(MAX(faiss_id), 0) FROM docs")
        max_id = cur.fetchone()[0]
        
        faiss_ids = np.array(range(max_id + 1, max_id + 1 + len(docs)), dtype=np.int64)
        self.index.add_with_ids(embs.astype('float32'), faiss_ids)
        
        for i, doc in enumerate(docs):
            cur.execute("INSERT OR REPLACE INTO docs (id, text, metadata, faiss_id) VALUES (?, ?, ?, ?)",
                        (ids[i], doc["text"], json.dumps(doc.get("metadata", {})), int(faiss_ids[i])))
        self.conn.commit()
        faiss.write_index(self.index, INDEX_FILE)

    def query(self, q, k=5, top_k=None):
        if top_k is not None:
            k = top_k
        q_emb = self.model.encode([q], convert_to_numpy=True).astype('float32')
        faiss.normalize_L2(q_emb)
        D, I = self.index.search(q_emb, k)
        
        results = []
        cur = self.conn.cursor()
        for i, idx in enumerate(I[0]):
            if idx == -1:
                continue
            cur.execute("SELECT id, text, metadata FROM docs WHERE faiss_id = ?", (int(idx),))
            row = cur.fetchone()
            if row:
                results.append({"id": row[0], "text": row[1], "metadata": json.loads(row[2]), "score": float(D[0][i])})
        return results

if __name__ == "__main__":
    print("Initializing P3 FAISS Worker...")
    worker = P3Worker()
    docs = [
        {"text": "Apple Silicon M3 Max has 128GB of unified memory.", "metadata": {"source": "hardware"}},
        {"text": "FastAPI is a modern, fast web framework for building APIs with Python.", "metadata": {"source": "software"}},
        {"text": "FAISS is a library for efficient similarity search and clustering of dense vectors.", "metadata": {"source": "software"}}
    ]
    print("Adding documents...")
    worker.add_documents(docs)
    print("Querying 'machine learning framework'...")
    res = worker.query("machine learning framework", k=1)
    print("Result:", res)
