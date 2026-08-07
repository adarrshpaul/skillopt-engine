import os
import sys
import time
from pathlib import Path
from typing import List, Dict, Any, Optional

try:
    import chromadb
    from chromadb.config import Settings
    CHROMADB_AVAILABLE = True
except ImportError:
    chromadb = None
    CHROMADB_AVAILABLE = False

class ChromaVectorMemory:
    """
    Lightweight, local ChromaDB semantic memory client for the SkillOpt Agent Harness.
    Supports connecting to a remote Chroma server or running with embedded local disk persistence.
    """
    def __init__(self, persist_path: str = "/Users/adarrsh/workspace/chroma_data", host: Optional[str] = None, port: int = 8000):
        self.persist_path = Path(persist_path)
        self.host = host
        self.port = port
        self.client = None
        self.collection = None
        
        if CHROMADB_AVAILABLE:
            self._init_client()

    def _init_client(self):
        try:
            if self.host:
                print(f"🔌 Connecting to Chroma HTTP Server at {self.host}:{self.port}...")
                self.client = chromadb.HttpClient(host=self.host, port=self.port)
            else:
                self.persist_path.mkdir(parents=True, exist_ok=True)
                self.client = chromadb.PersistentClient(path=str(self.persist_path))
            
            self.collection = self.client.get_or_create_collection(
                name="skillopt_codebase_memory",
                metadata={"description": "Semantic code and documentation index for SkillOpt"}
            )
            print(f"✅ ChromaDB Initialized (Collection: 'skillopt_codebase_memory', Items: {self.collection.count()})")
        except Exception as e:
            print(f"⚠️ ChromaDB initialization fallback: {e}")
            self.client = None
            self.collection = None

    def add_document(self, doc_id: str, text: str, metadata: Optional[Dict[str, Any]] = None):
        """Indexes a text or code document into the vector store."""
        if not self.collection:
            return False
        try:
            self.collection.upsert(
                ids=[doc_id],
                documents=[text],
                metadatas=[metadata or {"timestamp": time.time()}]
            )
            return True
        except Exception as e:
            print(f"Error indexing doc into Chroma: {e}")
            return False

    def semantic_search(self, query: str, n_results: int = 3) -> List[Dict[str, Any]]:
        """Performs vector similarity search across indexed codebase memory."""
        if not self.collection or self.collection.count() == 0:
            return []
        try:
            res = self.collection.query(
                query_texts=[query],
                n_results=min(n_results, self.collection.count())
            )
            results = []
            if res and res["documents"]:
                for i in range(len(res["documents"][0])):
                    results.append({
                        "id": res["ids"][0][i],
                        "document": res["documents"][0][i],
                        "metadata": res["metadatas"][0][i] if res["metadatas"] else {},
                        "distance": res["distances"][0][i] if "distances" in res and res["distances"] else 0.0
                    })
            return results
        except Exception as e:
            print(f"Error querying Chroma vector store: {e}")
            return []

    def index_workspace_files(self, workspace_dir: str = "/Users/adarrsh/workspace"):
        """Batch indexes all core workspace files into Chroma semantic memory."""
        ws = Path(workspace_dir)
        indexed_count = 0
        extensions = {".py", ".md", ".json"}
        
        for p in ws.glob("*.*"):
            if p.suffix in extensions and p.is_file() and p.stat().st_size < 50000:
                try:
                    content = p.read_text(encoding="utf-8", errors="ignore")
                    if content.strip():
                        self.add_document(
                            doc_id=p.name,
                            text=content[:2000], # Index first 2K chars
                            metadata={"filename": p.name, "path": str(p), "size": len(content)}
                        )
                        indexed_count += 1
                except Exception:
                    pass
        print(f"📦 Indexed {indexed_count} files into Chroma Semantic Vector Store.")
        return indexed_count

if __name__ == "__main__":
    memory = ChromaVectorMemory()
    memory.index_workspace_files()
    
    query = "Where is the Evaluator-Optimizer loop and AST validation?"
    print(f"\n🔍 Querying Chroma for: '{query}'")
    hits = memory.semantic_search(query, n_results=2)
    for hit in hits:
        print(f"  • Hit [{hit['id']}]: {hit['document'][:120]}...")
