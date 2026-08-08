"""
SkillOpt Engine — Unified Master Cockpit API Gateway & Web Server
===================================================================
Runs on Port 5002. Single Ingress for:
- Graph Chat API (/api/chat, /api/graph, /api/resume)
- Admission Control & Telemetry (/admit, /api/telemetry)
- Projects & IDE Explorer (/api/projects, /api/interactions, /api/files, /api/file, /api/mcts_tree)
- Model Fleet Governance (/api/fleet)
- Static Frontend SPA (/)
"""
import os
import sys
import json
import time
import uuid
import sqlite3
import threading
import subprocess
from typing import Optional, Dict, Any, List
from urllib.request import Request as URLRequest, urlopen

import grpc
from fastapi import FastAPI, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

import graph_store
import model_router
from admission_controller_grpc import AdmissionControllerServicer, HealthServicer, PREEMPTIONS, P1_TOKENS, P2_QUEUE_LEN, P3_PENDING
from proto import admission_pb2, admission_pb2_grpc
from proto import worker_pb2, worker_pb2_grpc

app = FastAPI(title="SkillOpt Master Cockpit", version="2.1")

# Initialize graph database
graph_store.init_db()

# Shared Admission Controller instance
controller = AdmissionControllerServicer()

# Projects Database path
PROJECTS_DB = "/Users/adarrsh/workspace/projects.db"

def init_projects_db():
    conn = sqlite3.connect(PROJECTS_DB)
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS projects (
        id TEXT PRIMARY KEY,
        name TEXT,
        created_at REAL
    )""")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS interactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        task_prompt TEXT,
        status TEXT,
        latency_ms REAL,
        code_output TEXT,
        timestamp REAL
    )""")
    conn.commit()
    conn.close()

init_projects_db()

# Models
class ChatRequest(BaseModel):
    id: Optional[str] = None
    text: str
    priority: int = 1

class ResumeRequest(BaseModel):
    checkpoint_token: str

class AdmitReq(BaseModel):
    id: Optional[str] = None
    priority: int = 1
    payload: str = ""

class FileSaveRequest(BaseModel):
    path: str
    content: str

# -----------------------------------------------------------------------------
# 1. GRAPH CHAT & LLM ROUTING ENDPOINTS
# -----------------------------------------------------------------------------

@app.post("/api/chat")
def api_chat(req: ChatRequest):
    req_id = req.id or f"req-{uuid.uuid4().hex[:8]}"
    prompt_node_id = f"prompt-{uuid.uuid4().hex[:8]}"
    response_node_id = f"resp-{uuid.uuid4().hex[:8]}"
    
    # 1. Admit via internal controller
    admit_res = controller._admit({'id': req_id, 'priority': req.priority, 'payload': req.text})
    action = admit_res.get('action', 'start')
    reason = admit_res.get('reason', 'token')
    
    # 2. Call Real LLM (Ornith on :8800 or Ling on :8801) - NO MOCKS ALLOWED
    # Use Planner (Ling) for all orchestration/talking, reserve Coder (Ornith) for coding
    is_coding_query = any(w in req.text.lower() for w in ["code", "script", "function", "implement", "debug", "python", "html", "javascript"])
    role = "coder" if is_coding_query else "planner"
    model_name = model_router.get_model(role)
    endpoint_url = model_router.get_endpoint(role)
    
    sys_prompt = (
        "You are Ling-3.0-Flash, a Master Software Architect. Decompose goals and generate clear, production plans and instructions."
        if role == "planner"
        else "You are Ornith-9B, an Expert Coding AI. Generate clean, functional, production Python/HTML/JS code."
    )
    
    try:
        payload = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": req.text}
            ],
            "temperature": 0.2,
            "max_tokens": 1024
        }
        http_req = URLRequest(endpoint_url, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"})
        with urlopen(http_req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if "choices" in data and len(data["choices"]) > 0:
                llm_response = data["choices"][0]["message"]["content"].strip()
            else:
                llm_response = data.get("text", "").strip()
    except Exception as err:
        # Fallback to secondary role endpoint if primary is down
        fallback_role = "coder" if role == "planner" else "planner"
        fallback_model = model_router.get_model(fallback_role)
        fallback_url = model_router.get_endpoint(fallback_role)
        try:
            payload["model"] = fallback_model
            http_req = URLRequest(fallback_url, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"})
            with urlopen(http_req, timeout=120) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if "choices" in data and len(data["choices"]) > 0:
                    llm_response = data["choices"][0]["message"]["content"].strip()
                else:
                    llm_response = data.get("text", "").strip()
                model_name = fallback_model
        except Exception:
            raise HTTPException(
                status_code=503,
                detail=f"Model Inference Server Offline ({endpoint_url} / {model_name}). Please start the model server via 'make run-local' or 'python steer_server.py'. Zero mocks allowed in production."
            )
    
    # 3. Save prompt and response to graph store
    graph_store.add_node(
        node_id=prompt_node_id,
        node_type="prompt",
        content=req.text,
        priority=req.priority,
        status="completed"
    )
    graph_store.add_node(
        node_id=response_node_id,
        node_type="response",
        content=llm_response,
        model=model_name,
        priority=req.priority,
        status="completed",
        metadata={"model": model_name}
    )
    graph_store.add_edge(
        src=prompt_node_id,
        dst=response_node_id,
        label="generates"
    )
    
    return {
        "node_id": response_node_id,
        "action": action,
        "reason": reason
    }

@app.get("/api/graph")
def get_graph():
    return graph_store.get_graph()

@app.post("/api/resume")
def api_resume(req: ResumeRequest):
    try:
        channel = grpc.insecure_channel('localhost:50052')
        stub = worker_pb2_grpc.WorkerStub(channel)
        resume_req = worker_pb2.ResumeRequest(checkpoint_token=req.checkpoint_token)
        resume_res = stub.Resume(resume_req)
        status = resume_res.status
    except Exception as e:
        status = f"error: {str(e)}"
    
    return {"status": status}

# -----------------------------------------------------------------------------
# 2. ADMISSION & TELEMETRY ENDPOINTS
# -----------------------------------------------------------------------------

@app.post("/admit")
def admit_http(req: AdmitReq):
    res = controller._admit({'id': req.id or f"req-{int(time.time()*1000)}", 'priority': req.priority, 'payload': req.payload})
    return res

@app.get("/api/telemetry")
def get_telemetry():
    p1 = round(controller.p1_bucket.available(), 1)
    p2 = controller.p2_queue.qsize()
    p3 = controller.p3_queue.qsize()
    preempted = controller.preempted_tasks
    preemptions_val = 0
    try:
        preemptions_val = int(PREEMPTIONS._value.get())
    except Exception:
        pass
    
    return {
        "p1_tokens": p1,
        "p2_queue_length": p2,
        "p3_pending_jobs": p3,
        "total_preemptions": preemptions_val,
        "preempted_tasks": [{"task_id": k, "checkpoint_token": v} for k, v in preempted.items()]
    }

# -----------------------------------------------------------------------------
# 3. PROJECTS & IDE ENDPOINTS
# -----------------------------------------------------------------------------

@app.get("/api/projects")
def get_projects():
    conn = sqlite3.connect(PROJECTS_DB)
    cur = conn.cursor()
    cur.execute("SELECT id, name, created_at FROM projects ORDER BY created_at DESC")
    rows = cur.fetchall()
    conn.close()
    return [{"id": r[0], "name": r[1], "created_at": r[2]} for r in rows]

@app.get("/api/interactions")
def get_interactions():
    conn = sqlite3.connect(PROJECTS_DB)
    cur = conn.cursor()
    cur.execute("SELECT id, task_prompt, status, latency_ms, code_output, timestamp FROM interactions ORDER BY timestamp DESC LIMIT 50")
    rows = cur.fetchall()
    conn.close()
    return [{
        "id": r[0], "task_prompt": r[1], "status": r[2],
        "latency_ms": r[3], "code_output": r[4], "timestamp": r[5]
    } for r in rows]

@app.get("/api/mcts_tree")
def get_mcts_tree():
    dataset_path = "/Users/adarrsh/workspace/dpo_graph_dataset.jsonl"
    pairs = []
    if os.path.exists(dataset_path):
        with open(dataset_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        pairs.append(json.loads(line))
                    except Exception:
                        pass
    return {
        "nodes_count": len(pairs) * 3,
        "pairs_count": len(pairs),
        "pairs": pairs
    }

@app.get("/api/files")
def get_workspace_files():
    workspace_dir = "/Users/adarrsh/workspace"
    files_list = []
    try:
        res = subprocess.run(
            ["git", "ls-files", "-c", "-o", "--exclude-standard"],
            cwd=workspace_dir,
            capture_output=True,
            text=True,
            check=True
        )
        for line in res.stdout.splitlines():
            if line.strip() and not line.startswith((".", "ml-env", "chroma_data")):
                files_list.append(line.strip())
    except Exception:
        for root, dirs, files in os.walk(workspace_dir):
            if any(p in root for p in [".git", ".tasks", "__pycache__", "ml-env", "chroma_data"]):
                continue
            for file in files:
                if file.endswith((".py", ".md", ".json", ".jsonl", ".txt", ".html", ".sh")):
                    rel_path = os.path.relpath(os.path.join(root, file), workspace_dir)
                    files_list.append(rel_path)
    return {"files": sorted(files_list)}

@app.get("/api/file")
def read_file(path: str):
    full_path = os.path.join("/Users/adarrsh/workspace", path)
    if not os.path.abspath(full_path).startswith("/Users/adarrsh/workspace"):
        raise HTTPException(status_code=403, detail="Access denied")
    if not os.path.exists(full_path):
        raise HTTPException(status_code=404, detail="File not found")
    with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
        return {"path": path, "content": f.read()}

@app.post("/api/file")
def save_file(req: FileSaveRequest):
    full_path = os.path.join("/Users/adarrsh/workspace", req.path)
    if not os.path.abspath(full_path).startswith("/Users/adarrsh/workspace"):
        raise HTTPException(status_code=403, detail="Access denied")
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    with open(full_path, "w", encoding="utf-8") as f:
        f.write(req.content)
    return {"status": "saved", "path": req.path}

# -----------------------------------------------------------------------------
# 4. MODEL FLEET GOVERNANCE ENDPOINT
# -----------------------------------------------------------------------------

@app.get("/api/fleet")
def get_fleet():
    return {
        "roles": model_router.ROLES,
        "planner": model_router.get_model("planner"),
        "coder": model_router.get_model("coder"),
        "reviewer": model_router.get_model("reviewer"),
        "fallback": model_router.get_model("fallback")
    }

# Mount static directory
static_dir = "/Users/adarrsh/workspace/static"
os.makedirs(static_dir, exist_ok=True)
app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")


def start_grpc_server():
    try:
        from concurrent import futures
        server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
        admission_pb2_grpc.add_AdmissionServiceServicer_to_server(controller, server)
        admission_pb2_grpc.add_HealthServicer_to_server(HealthServicer(), server)
        server.add_insecure_port('[::]:50051')
        server.start()
        print("⚡ [Master Cockpit] gRPC Admission Server listening on port 50051", flush=True)
    except Exception as e:
        print(f"⚠️ [Master Cockpit] Could not start gRPC server: {e}", flush=True)


if __name__ == "__main__":
    import uvicorn
    threading.Thread(target=start_grpc_server, daemon=True).start()
    print("🚀 [Master Cockpit] Starting Unified Web UI on http://0.0.0.0:5002", flush=True)
    uvicorn.run("master_cockpit:app", host="0.0.0.0", port=5002, reload=True)
