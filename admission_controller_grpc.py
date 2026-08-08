"""
Admission Controller with gRPC, Prometheus Metrics, Preemption & Flask UI
========================================================================
Runs:
- gRPC server on port 50051 (AdmissionService & Health)
- HTTP Flask UI on port 5001 (Interactive dashboard & REST /admit)
- Prometheus metrics on port 8001
- P2 Task Preemption with Checkpoint Token tracking
"""

import time
import threading
import logging
import uuid
from queue import Queue, Empty
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Any, Optional

# Metrics
try:
    from prometheus_client import start_http_server, Gauge, Counter
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False
    class Gauge:
        def __init__(self, *args, **kwargs): pass
        def set(self, val): pass
        def inc(self, val=1): pass
        def dec(self, val=1): pass
    class Counter:
        def __init__(self, *args, **kwargs): pass
        def inc(self, val=1): pass
        def labels(self, *args, **kwargs): return self

try:
    import psutil
except ImportError:
    psutil = None

try:
    from fastapi import FastAPI, Request
    from fastapi.responses import HTMLResponse, JSONResponse
    import uvicorn
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False

try:
    import grpc
    from concurrent import futures
    GRPC_AVAILABLE = True
except ImportError:
    grpc = None
    futures = None
    GRPC_AVAILABLE = False

# Import local protobuf stubs
try:
    from proto import admission_pb2, admission_pb2_grpc
except ImportError:
    import admission_pb2, admission_pb2_grpc

# Optional NVML for GPU memory percent
try:
    import pynvml
    pynvml.nvmlInit()
    NVML_ENABLED = True
    nvml_handle = pynvml.nvmlDeviceGetHandleByIndex(0)
except Exception:
    NVML_ENABLED = False
    nvml_handle = None

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger("AdmissionControllerGRPC")

# Prometheus Metrics Definitions
P1_TOKENS = Gauge('p1_tokens', 'Available P1 tokens')
P2_QUEUE_LEN = Gauge('p2_queue_length', 'P2 queue length')
P3_PENDING = Gauge('p3_pending_jobs', 'P3 pending jobs')
PREEMPTIONS = Counter('preemptions_total', 'Total preemptions')
ADMISSIONS = Counter('admissions_total', 'Total admissions', ['priority', 'result'])


class TokenBucket:
    """Thread-safe Token Bucket rate limiter."""
    def __init__(self, rate: float = 10.0, burst: float = 20.0):
        self.rate = rate
        self.capacity = burst
        self.tokens = burst
        self.lock = threading.Lock()
        self.last = time.time()

    def consume(self, n: float = 1.0) -> bool:
        with self.lock:
            now = time.time()
            delta = now - self.last
            self.tokens = min(self.capacity, self.tokens + delta * self.rate)
            self.last = now
            if self.tokens >= n:
                self.tokens -= n
                return True
            return False

    def available(self) -> float:
        with self.lock:
            now = time.time()
            delta = now - self.last
            self.tokens = min(self.capacity, self.tokens + delta * self.rate)
            self.last = now
            return self.tokens


class AdmissionControllerServicer:
    """Core Admission Controller implementing gRPC, preemption, and queue governance."""
    def __init__(self):
        self.p1_bucket = TokenBucket(rate=10, burst=20)
        self.p1_preempt_budget = 5
        self.p1_budget_reset_time = time.time() + 60.0
        self.p2_queue = Queue(maxsize=50)
        self.p2_executor = ThreadPoolExecutor(max_workers=2)
        self.p3_queue = Queue()
        self.hysteresis = {'throttle_on': 0.80, 'resume_at': 0.70, 'hold_seconds': 30}
        self.p3_throttled_until = 0.0
        self.lock = threading.Lock()
        self.preempted_tasks: Dict[str, str] = {}  # task_id -> checkpoint_token
        self.audit_records = []
        self.start_background_workers()

    def composite_util(self) -> float:
        host_mem = psutil.virtual_memory().percent / 100.0 if psutil else 0.35
        cpu = 0.15
        if psutil:
            try:
                cpu = min(1.0, psutil.getloadavg()[0] / (psutil.cpu_count() or 1))
            except Exception:
                cpu = 0.15
        gpu = 0.0
        if NVML_ENABLED and nvml_handle:
            try:
                info = pynvml.nvmlDeviceGetMemoryInfo(nvml_handle)
                gpu = info.used / info.total
            except Exception:
                gpu = 0.0
        return max(host_mem, cpu, gpu)

    def can_run_p3(self) -> bool:
        now = time.time()
        util = self.composite_util()
        if now < self.p3_throttled_until:
            return False
        if util > self.hysteresis['throttle_on']:
            self.p3_throttled_until = now + self.hysteresis['hold_seconds']
            return False
        return util < 0.65

    def Admit(self, request_proto, context=None):
        """gRPC Admit implementation."""
        req_id = getattr(request_proto, 'id', f"req-{int(time.time()*1000)}")
        priority = getattr(request_proto, 'priority', 1)
        payload = getattr(request_proto, 'payload', "")
        
        req = {'id': req_id, 'priority': priority, 'payload': payload}
        result = self._admit(req)
        
        # Update metrics
        P1_TOKENS.set(self.p1_bucket.available())
        P2_QUEUE_LEN.set(self.p2_queue.qsize())
        P3_PENDING.set(self.p3_queue.qsize())

        return admission_pb2.AdmitResponse(
            action=result.get('action', ''),
            reason=result.get('reason', ''),
            checkpoint_token=result.get('checkpoint_token', ''),
            code=result.get('code', '')
        )

    def _admit(self, req: Dict[str, Any]) -> Dict[str, Any]:
        pr = req.get('priority', 1)
        req_id = req.get('id', f"req-{int(time.time()*1000)}")
        
        # Reset preemption budget every 60s
        now = time.time()
        if now > self.p1_budget_reset_time:
            self.p1_preempt_budget = 5
            self.p1_budget_reset_time = now + 60.0

        if pr == 1:
            if self.p1_bucket.consume(1):
                ADMISSIONS.labels(priority='1', result='accepted').inc()
                logging.info(f"P1 accepted {req_id}")
                return {'action': 'start', 'reason': 'token'}
            elif self.p1_preempt_budget > 0 and self._preempt_p2():
                self.p1_preempt_budget -= 1
                PREEMPTIONS.inc()
                ADMISSIONS.labels(priority='1', result='preempted').inc()
                checkpoint_tok = self.preempted_tasks.get(req_id, str(uuid.uuid4()))
                logging.info(f"P1 preempted for {req_id} (Checkpoint: {checkpoint_tok})")
                return {'action': 'start', 'reason': 'preempt', 'checkpoint_token': checkpoint_tok}
            else:
                ADMISSIONS.labels(priority='1', result='rejected').inc()
                return {'action': 'reject', 'code': 'P1_RATE_LIMIT'}

        if pr == 2:
            try:
                self.p2_queue.put_nowait(req)
                P2_QUEUE_LEN.set(self.p2_queue.qsize())
                ADMISSIONS.labels(priority='2', result='queued').inc()
                logging.info(f"P2 queued {req_id}")
                return {'action': 'queued'}
            except Exception:
                ADMISSIONS.labels(priority='2', result='rejected').inc()
                return {'action': 'reject', 'code': 'P2_QUEUE_FULL'}

        if pr == 3:
            if self.can_run_p3():
                self.p3_queue.put(req)
                P3_PENDING.set(self.p3_queue.qsize())
                ADMISSIONS.labels(priority='3', result='scheduled').inc()
                logging.info(f"P3 scheduled {req_id}")
                return {'action': 'scheduled'}
            else:
                ADMISSIONS.labels(priority='3', result='throttled').inc()
                return {'action': 'reject', 'code': 'P3_THROTTLED'}

        return {'action': 'reject', 'code': 'INVALID_PRIORITY'}

    def _preempt_p2(self) -> bool:
        with self.lock:
            try:
                task = self.p2_queue.get_nowait()
                checkpoint_token = f"ckpt-{task.get('id', 'p2')}-{int(time.time())}"
                self.preempted_tasks[task.get('id')] = checkpoint_token
                P2_QUEUE_LEN.set(self.p2_queue.qsize())
                logging.info(f"Preempted P2 task {task.get('id')} -> checkpoint {checkpoint_token}")
                return True
            except Empty:
                return False

    def start_background_workers(self):
        def p2_worker():
            while True:
                req = self.p2_queue.get()
                P2_QUEUE_LEN.set(self.p2_queue.qsize())
                task_id = req.get('id')
                logging.info(f"Running P2 task {task_id}")
                for step in range(10):
                    if task_id in self.preempted_tasks:
                        token = self.preempted_tasks.pop(task_id, None)
                        logging.info(f"Worker checkpointed {task_id} -> {token}")
                        break
                    time.sleep(0.2)
                logging.info(f"P2 task {task_id} finished or checkpointed")
                self.p2_queue.task_done()

        def p3_worker():
            while True:
                req = self.p3_queue.get()
                P3_PENDING.set(self.p3_queue.qsize())
                logging.info(f"Running P3 task {req.get('id')}")
                time.sleep(0.5)
                self.p3_queue.task_done()

        threading.Thread(target=p2_worker, daemon=True).start()
        threading.Thread(target=p3_worker, daemon=True).start()


class HealthServicer:
    """gRPC Health service."""
    def Check(self, request_proto, context=None):
        return admission_pb2.HealthCheckResponse(status='SERVING')


# FastAPI Web UI
if FASTAPI_AVAILABLE:
    app = FastAPI()
    controller = AdmissionControllerServicer()

    UI_TEMPLATE = """
    <!doctype html>
    <html lang="en">
    <head>
      <meta charset="utf-8">
      <title>Admission Controller Dashboard</title>
      <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0f172a; color: #f8fafc; margin: 0; padding: 24px; }
        .container { max-width: 900px; margin: 0 auto; background: #1e293b; padding: 28px; border-radius: 12px; border: 1px solid #334155; }
        h2 { color: #38bdf8; margin-top: 0; }
        .grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin: 24px 0; }
        .card { background: #0f172a; padding: 16px; border-radius: 8px; border: 1px solid #334155; text-align: center; }
        .card-val { font-size: 28px; font-weight: bold; color: #4ade80; margin-top: 8px; }
        .card-lbl { font-size: 12px; color: #94a3b8; text-transform: uppercase; }
        ul { list-style: none; padding: 0; }
        li { background: #0f172a; padding: 12px 16px; margin-bottom: 8px; border-radius: 6px; border-left: 4px solid #38bdf8; font-family: monospace; font-size: 13px; }
      </style>
    </head>
    <body>
      <div class="container">
        <h2>⚡ Admission Controller & Preemption Engine</h2>
        <div class="grid">
          <div class="card"><div class="card-lbl">P1 Tokens Available</div><div class="card-val">{p1}</div></div>
          <div class="card"><div class="card-lbl">P2 Queue Length</div><div class="card-val">{p2}</div></div>
          <div class="card"><div class="card-lbl">P3 Pending Jobs</div><div class="card-val">{p3}</div></div>
          <div class="card"><div class="card-lbl">Total Preemptions</div><div class="card-val" style="color: #f87171;">{preemptions}</div></div>
        </div>

        <h3>🔄 Recent Preempted Tasks & Checkpoint Tokens</h3>
        <ul>
        {preempted_items}
        </ul>
      </div>
    </body>
    </html>
    """

    @app.get("/", response_class=HTMLResponse)
    def index():
        p1 = round(controller.p1_bucket.available(), 1)
        p2 = controller.p2_queue.qsize()
        p3 = controller.p3_queue.qsize()
        preempted = controller.preempted_tasks
        preemptions_val = 0
        try:
            preemptions_val = PREEMPTIONS._value.get()
        except Exception:
            pass
        
        preempted_items = "".join(f"<li><strong>Task ID:</strong> {k} &nbsp;➔&nbsp; <span style='color: #facc15;'>Checkpoint: {v}</span></li>" for k, v in preempted.items()) or "<li style='color: #94a3b8;'>No active preempted tasks. System running nominal.</li>"
        
        html = UI_TEMPLATE.format(p1=p1, p2=p2, p3=p3, preemptions=int(preemptions_val), preempted_items=preempted_items)
        return HTMLResponse(content=html, status_code=200)

    @app.post("/admit")
    async def admit_http(request: Request):
        try:
            req = await request.json()
        except Exception:
            req = {}
        res = controller._admit(req)
        P1_TOKENS.set(controller.p1_bucket.available())
        return JSONResponse(content=res)


def serve_grpc():
    if GRPC_AVAILABLE:
        server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
        admission_pb2_grpc.add_AdmissionServiceServicer_to_server(controller, server)
        admission_pb2_grpc.add_HealthServicer_to_server(HealthServicer(), server)
        server.add_insecure_port('[::]:50051')
        server.start()
        logging.info('gRPC server started on port 50051')
        server.wait_for_termination()


if __name__ == '__main__':
    if PROMETHEUS_AVAILABLE:
        try:
            start_http_server(8001)
            logging.info('Prometheus metrics exporter started on port 8001')
        except Exception as e:
            logging.warning(f"Could not start Prometheus server on 8001: {e}")

    threading.Thread(target=serve_grpc, daemon=True).start()
    
    if FASTAPI_AVAILABLE:
        logging.info("FastAPI Web UI started on http://0.0.0.0:5001")
        uvicorn.run(app, host='0.0.0.0', port=5001)
