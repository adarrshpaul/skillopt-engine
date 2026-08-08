import os
import uuid
import grpc
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional

import graph_store
from proto import admission_pb2, admission_pb2_grpc
from proto import worker_pb2, worker_pb2_grpc

import model_router
from urllib.request import Request, urlopen
import json

app = FastAPI()

# Initialize graph database
graph_store.init_db()

class ChatRequest(BaseModel):
    id: Optional[str] = None
    text: str
    priority: int = 1

class ResumeRequest(BaseModel):
    checkpoint_token: str

@app.post("/api/chat")
def api_chat(req: ChatRequest):
    req_id = req.id or f"req-{uuid.uuid4().hex[:8]}"
    prompt_node_id = f"prompt-{uuid.uuid4().hex[:8]}"
    response_node_id = f"resp-{uuid.uuid4().hex[:8]}"
    
    # 1. Call admission controller gRPC endpoint
    try:
        channel = grpc.insecure_channel('localhost:50051')
        stub = admission_pb2_grpc.AdmissionServiceStub(channel)
        admit_req = admission_pb2.AdmitRequest(
            id=req_id,
            priority=req.priority,
            payload=req.text
        )
        admit_res = stub.Admit(admit_req)
        action = admit_res.action
        reason = admit_res.reason
    except Exception as e:
        action = "error"
        reason = str(e)
    
    # 2. Call LLM (Ornith/Coder via model_router) with fallback
    model_name = model_router.get_model("coder")
    endpoint_url = model_router.get_endpoint("coder")
    
    llm_response = f"This is a mocked LLM response for your query: '{req.text}'"
    try:
        payload = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": "You are Ornith-9B, an Expert Coding AI."},
                {"role": "user", "content": req.text}
            ],
            "temperature": 0.2,
            "max_tokens": 1024
        }
        http_req = Request(endpoint_url, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"})
        with urlopen(http_req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            llm_response = data["choices"][0]["message"]["content"].strip()
    except Exception:
        pass # Graceful fallback to mock response
    
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

# Ensure static directory exists
static_dir = "/Users/adarrsh/workspace/static"
os.makedirs(static_dir, exist_ok=True)

# Mount static files at root
app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("graph_api_server:app", host="0.0.0.0", port=5002, reload=True)
