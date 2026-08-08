"""
P2 Worker Stub — Demonstrating Checkpoint and Resume gRPC Contract
=================================================================
Implements:
- Preempt(PreemptRequest) -> PreemptResponse(checkpoint_token)
- Resume(ResumeRequest) -> ResumeResponse(status)
- gRPC server on port 50052
"""

import time
import threading
import logging
import json
import os
import uuid
import fcntl
from concurrent import futures
from typing import Dict, Any

CHECKPOINT_FILE = "checkpoints.json"
_lock = threading.Lock()

def _read_checkpoints():
    if not os.path.exists(CHECKPOINT_FILE) or os.path.getsize(CHECKPOINT_FILE) == 0:
        return {}
    try:
        with open(CHECKPOINT_FILE, "r", encoding="utf-8") as f:
            content = f.read().strip()
            if not content:
                return {}
            return json.loads(content)
    except Exception as e:
        logging.warning(f"Failed to read checkpoints: {e}")
        return {}

def _write_checkpoints(data):
    tmp = f"{CHECKPOINT_FILE}.{uuid.uuid4().hex}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, CHECKPOINT_FILE)

def save_checkpoint(token, task_id, progress, metadata=None):
    with _lock:
        lock_file = CHECKPOINT_FILE + ".lock"
        with open(lock_file, "w") as lf:
            fcntl.flock(lf, fcntl.LOCK_EX)
            try:
                data = _read_checkpoints()
                data[token] = {
                    "task_id": task_id,
                    "progress": progress,
                    "metadata": metadata or {},
                    "timestamp": time.time()
                }
                _write_checkpoints(data)
            finally:
                fcntl.flock(lf, fcntl.LOCK_UN)

def load_checkpoint(token):
    with _lock:
        data = _read_checkpoints()
        return data.get(token)

try:
    import grpc
    GRPC_AVAILABLE = True
except ImportError:
    grpc = None
    GRPC_AVAILABLE = False

try:
    from proto import worker_pb2, worker_pb2_grpc
except ImportError:
    import worker_pb2, worker_pb2_grpc

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger("P2WorkerStub")


class WorkerServicer:
    """Worker implementation honoring checkpointing and state resumption."""
    def __init__(self):
        pass

    def Preempt(self, request, context=None):
        task_id = getattr(request, 'task_id', 'task-default')
        progress = getattr(request, 'progress', '50%')
        token = f"{task_id}-ckpt-{int(time.time()*1000)}"
        save_checkpoint(token, task_id, progress)
        logger.info(f"💾 [Checkpoint Created] Token: {token} | Progress: {progress}")
        return worker_pb2.PreemptResponse(checkpoint_token=token)

    def Resume(self, request, context=None):
        token = getattr(request, 'checkpoint_token', '')
        state = load_checkpoint(token)
        if not state:
            logger.warning(f"⚠️ [Resume Failed] Token '{token}' not found.")
            return worker_pb2.ResumeResponse(status='NOT_FOUND')
        
        logger.info(f"🔄 [Resuming Work] Token: {token} from state: {state}")
        time.sleep(0.5)  # simulate resuming execution
        return worker_pb2.ResumeResponse(status='RESUMED')


def serve(port: int = 50052):
    if GRPC_AVAILABLE:
        server = grpc.server(futures.ThreadPoolExecutor(max_workers=4))
        worker_pb2_grpc.add_WorkerServicer_to_server(WorkerServicer(), server)
        server.add_insecure_port(f'[::]:{port}')
        server.start()
        logger.info(f"Worker gRPC server listening on port {port}")
        server.wait_for_termination()
    else:
        logger.info("Running standalone WorkerServicer mock loop")
        w = WorkerServicer()
        tok = w.Preempt(worker_pb2.PreemptRequest(task_id="task-101", progress="Step 3/5")).checkpoint_token
        res = w.Resume(worker_pb2.ResumeRequest(checkpoint_token=tok)).status
        logger.info(f"Worker mock execution verified: {res}")


if __name__ == '__main__':
    serve()
