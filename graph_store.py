import sqlite3
import json
import time

DB_FILE = "graph.db"

def get_db():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS nodes (
        id TEXT PRIMARY KEY,
        type TEXT,
        content TEXT,
        model TEXT,
        priority INT,
        status TEXT,
        created_at REAL,
        metadata TEXT
    )""")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS edges (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        src TEXT,
        dst TEXT,
        label TEXT,
        created_at REAL
    )""")
    conn.commit()
    conn.close()

def add_node(node_id, node_type, content, model="", priority=1, status="completed", metadata=None):
    if metadata is None:
        metadata = {}
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
    INSERT OR REPLACE INTO nodes (id, type, content, model, priority, status, created_at, metadata)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (node_id, node_type, content, model, priority, status, time.time(), json.dumps(metadata)))
    conn.commit()
    conn.close()

def add_edge(src, dst, label):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
    INSERT INTO edges (src, dst, label, created_at)
    VALUES (?, ?, ?, ?)
    """, (src, dst, label, time.time()))
    conn.commit()
    conn.close()

def get_graph():
    conn = get_db()
    cur = conn.cursor()
    nodes = []
    for row in cur.execute("SELECT * FROM nodes ORDER BY created_at ASC"):
        nodes.append({
            "id": row["id"],
            "type": row["type"],
            "content": row["content"],
            "model": row["model"],
            "priority": row["priority"],
            "status": row["status"],
            "created_at": row["created_at"],
            "metadata": json.loads(row["metadata"]) if row["metadata"] else {}
        })
    
    edges = []
    for row in cur.execute("SELECT * FROM edges ORDER BY created_at ASC"):
        edges.append({
            "id": row["id"],
            "src": row["src"],
            "dst": row["dst"],
            "label": row["label"],
            "created_at": row["created_at"]
        })
    conn.close()
    return {"nodes": nodes, "edges": edges}

if __name__ == "__main__":
    init_db()
    print("Graph DB initialized.")
