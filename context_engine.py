import argparse
import json
import logging
import math
import os
import re
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Tuple

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def tokenize(text: str) -> List[str]:
    """Tokenize text by splitting on non-alphanumeric characters and lowercasing."""
    return [word for word in re.split(r'\W+', text.lower()) if word]

def compute_tf(tokens: List[str]) -> Dict[str, float]:
    """Compute term frequency (TF) for a list of tokens."""
    tf = defaultdict(int)
    for token in tokens:
        tf[token] += 1
    total_tokens = len(tokens)
    if total_tokens > 0:
        for token in tf:
            tf[token] /= total_tokens
    return dict(tf)

class TFIDF:
    """A pure Python implementation of TF-IDF."""
    def __init__(self):
        self.documents: List[Dict] = []
        self.idf: Dict[str, float] = {}
        self.corpus_size = 0
        self.tf_vectors: List[Dict[str, float]] = []

    def fit_transform(self, documents: List[Dict]):
        """Fit the TF-IDF model on the given documents and compute their TF vectors."""
        self.documents = documents
        self.corpus_size = len(documents)
        self.tf_vectors = []
        
        doc_freq = defaultdict(int)
        
        # Compute TF and Document Frequency
        for doc in documents:
            tokens = tokenize(doc['text'])
            tf = compute_tf(tokens)
            self.tf_vectors.append(tf)
            for token in tf.keys():
                doc_freq[token] += 1
                
        # Compute IDF
        self.idf = {}
        for token, freq in doc_freq.items():
            self.idf[token] = math.log((1 + self.corpus_size) / (1 + freq)) + 1

    def compute_tfidf_vector(self, text: str) -> Dict[str, float]:
        """Compute the TF-IDF vector for a given text."""
        tokens = tokenize(text)
        tf = compute_tf(tokens)
        tfidf_vector = {}
        for token, tf_val in tf.items():
            if token in self.idf:
                tfidf_vector[token] = tf_val * self.idf[token]
        return tfidf_vector

    def cosine_similarity(self, vec1: Dict[str, float], vec2: Dict[str, float]) -> float:
        """Compute cosine similarity between two sparse TF-IDF vectors."""
        intersection = set(vec1.keys()) & set(vec2.keys())
        dot_product = sum(vec1[k] * vec2[k] for k in intersection)
        
        norm1 = math.sqrt(sum(v ** 2 for v in vec1.values()))
        norm2 = math.sqrt(sum(v ** 2 for v in vec2.values()))
        
        if norm1 == 0.0 or norm2 == 0.0:
            return 0.0
        return dot_product / (norm1 * norm2)

    def search(self, query: str, top_k: int = 5) -> List[Tuple[int, float]]:
        """Search the indexed documents using the query and return top K results."""
        query_vector = self.compute_tfidf_vector(query)
        if not query_vector:
            return []
            
        scores = []
        for idx, doc_tf in enumerate(self.tf_vectors):
            doc_tfidf = {k: v * self.idf[k] for k, v in doc_tf.items()}
            score = self.cosine_similarity(query_vector, doc_tfidf)
            if score > 0:
                scores.append((idx, score))
                
        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:top_k]

class ContextEngine:
    """A lightweight RAG context engine for Project Ornith."""
    
    ALLOWED_EXTENSIONS = {'.py', '.md', '.sh', '.json', '.yaml', '.txt', '.html', '.css', '.js', '.ts', '.tsx'}
    IGNORED_DIRS = {'node_modules', '.git', '__pycache__', '.venv', 'auto-dev-env'}
    
    def __init__(self, workspace_dir: str = '/Users/adarrsh/workspace', trajectory_dir: str = None):
        self.workspace_dir = Path(workspace_dir)
        self.trajectory_dir = Path(trajectory_dir) if trajectory_dir else self.workspace_dir / '.tasks' / 'trajectories'
        self.documents = []
        self.tfidf = TFIDF()
        self.is_indexed = False

    def index_workspace(self):
        """Walks the workspace directory, reads text files, and adds them to documents."""
        logger.info(f"Indexing workspace: {self.workspace_dir}")
        count = 0
        for root, dirs, files in os.walk(self.workspace_dir):
            dirs[:] = [d for d in dirs if d not in self.IGNORED_DIRS]
            for file in files:
                path = Path(root) / file
                if path.suffix.lower() in self.ALLOWED_EXTENSIONS:
                    try:
                        with open(path, 'r', encoding='utf-8') as f:
                            lines = []
                            for i, line in enumerate(f):
                                if i >= 500:
                                    break
                                lines.append(line)
                            content = "".join(lines)
                            if content.strip():
                                self.documents.append({
                                    'type': 'file',
                                    'source': str(path),
                                    'text': content
                                })
                                count += 1
                    except Exception as e:
                        logger.debug(f"Failed to read file {path}: {e}")
        logger.info(f"Indexed {count} workspace files.")

    def index_trajectories(self):
        """Reads all .jsonl files from trajectories dir and indexes command+output pairs."""
        if not self.trajectory_dir.exists():
            logger.info(f"Trajectory directory {self.trajectory_dir} does not exist. Skipping.")
            return
            
        logger.info(f"Indexing trajectories from: {self.trajectory_dir}")
        count = 0
        for path in self.trajectory_dir.glob('*.jsonl'):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    for line in f:
                        try:
                            data = json.loads(line)
                            command = data.get('command', '')
                            output = data.get('output', '')
                            text = f"Command: {command}\nResult: {output}"
                            if text.strip():
                                self.documents.append({
                                    'type': 'trajectory',
                                    'source': path.name,
                                    'text': text
                                })
                                count += 1
                        except json.JSONDecodeError:
                            continue
            except Exception as e:
                logger.debug(f"Failed to read trajectory file {path}: {e}")
        logger.info(f"Indexed {count} trajectory entries.")

    def _build_index_if_needed(self):
        if not self.is_indexed:
            self.index_workspace()
            self.index_trajectories()
            self.tfidf.fit_transform(self.documents)
            self.is_indexed = True

    def retrieve(self, query: str, top_k: int = 5) -> List[Dict]:
        """Returns the top-K most relevant chunks."""
        self._build_index_if_needed()
        
        results = self.tfidf.search(query, top_k=top_k)
        retrieved = []
        for idx, score in results:
            doc = self.documents[idx]
            retrieved.append({
                'source_file': doc['source'],
                'type': doc['type'],
                'content': doc['text'][:500] + ('...' if len(doc['text']) > 500 else ''),
                'relevance_score': score
            })
        return retrieved

    def build_context(self, query: str, token_budget: int = 2048) -> str:
        """Retrieves relevant chunks and formats them into a context block."""
        retrieved = self.retrieve(query, top_k=20) # Fetch more, then filter by budget
        
        char_budget = token_budget * 4
        context_parts = ["=== RELEVANT CONTEXT ==="]
        current_chars = len(context_parts[0])
        
        for item in retrieved:
            if item['type'] == 'file':
                header = f"\n[File: {item['source_file']}]"
            else:
                header = f"\n[Trajectory: {item['source_file']}]"
                
            chunk = f"{header}\n{item['content']}\n"
            
            if current_chars + len(chunk) > char_budget:
                break
                
            context_parts.append(chunk)
            current_chars += len(chunk)
            
        context_parts.append("=== END CONTEXT ===")
        return "\n".join(context_parts)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Context Engine CLI")
    parser.add_argument('--query', type=str, required=True, help="Query to search for")
    parser.add_argument('--top-k', type=int, default=5, help="Number of results to retrieve")
    parser.add_argument('--token-budget', type=int, default=2048, help="Token budget for context")
    args = parser.parse_args()

    engine = ContextEngine()
    context = engine.build_context(args.query, token_budget=args.token_budget)
    print(context)
