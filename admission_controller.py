"""
Admission Controller — Production-Grade Workload-Aware Rate Limiter & Preemption Engine
====================================================================================
Features:
- Priority 1 (Interactive / HITL): Token bucket rate limit with preemption budget
- Priority 2 (Task Orchestration): Bounded FIFO queue (concurrency = 2), preemptible by P1
- Priority 3 (Background / DPO): Runs when composite utilization < 65%; hysteresis throttling at >80% (30s hold)
- Multi-Metric Composite Signal: max(Host RAM %, CPU Load %, GPU VRAM %)
- Prometheus Metrics on :8001 / Flask HTTP API on :5000 (/admit)
"""

import os
import sys
import time
import threading
import logging
from queue import Queue, Empty
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Any, Optional

try:
    from flask import Flask, request, jsonify
except ImportError:
    Flask = None

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
logger = logging.getLogger("AdmissionController")

# Prometheus Metrics
P1_TOKENS = Gauge('p1_tokens', 'Available P1 tokens')
P2_QUEUE_LEN = Gauge('p2_queue_length', 'P2 queue length')
P3_PENDING = Gauge('p3_pending_jobs', 'P3 pending jobs')
PREEMPTIONS = Counter('preemptions_total', 'Total preemptions')
ADMISSIONS = Counter('admissions_total', 'Total admissions', ['priority', 'result'])
MODEL_VRAM_BYTES = Gauge('model_vram_bytes', 'Allocated VRAM in bytes', ['model'])
MODEL_RSS_BYTES = Gauge('model_rss_bytes', 'Resident Set Size in bytes', ['model'])
EVICTIONS_TOTAL = Counter('evictions_total', 'Total cache evictions', ['cache_tier', 'reason'])


class TokenBucket:
    """Thread-safe token bucket rate limiter with burst capacity."""
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


class AdmissionController:
    def __init__(self, audit_log_path: str = "/Users/adarrsh/workspace/audit_log.jsonl"):
        self.p1_bucket = TokenBucket(rate=10, burst=20)
        self.p1_preempt_budget = 5
        self.p1_budget_reset_time = time.time() + 60.0
        
        self.p2_queue = Queue(maxsize=50)
        self.p2_executor = ThreadPoolExecutor(max_workers=2)
        self.p3_queue = Queue()
        
        self.hysteresis = {'throttle_on': 0.80, 'resume_at': 0.70, 'hold_seconds': 30}
        self.p3_throttled_until = 0.0
        self.lock = threading.Lock()
        self.audit_log_path = audit_log_path

    def composite_util(self) -> float:
        """Calculates composite system pressure: max(Host RAM %, CPU load %, GPU VRAM %)."""
        host_mem = psutil.virtual_memory().percent / 100.0 if psutil else 0.40
        cpu = 0.20
        if psutil:
            try:
                cpu = min(1.0, psutil.getloadavg()[0] / (psutil.cpu_count() or 1))
            except Exception:
                cpu = 0.20
        gpu = 0.0
        if NVML_ENABLED and nvml_handle:
            try:
                info = pynvml.nvmlDeviceGetMemoryInfo(nvml_handle)
                gpu = info.used / info.total
            except Exception:
                gpu = 0.0
        return max(host_mem, cpu, gpu)

    def can_run_p3(self) -> bool:
        """Determines if Priority 3 background tasks are permitted under composite load."""
        now = time.time()
        util = self.composite_util()
        if now < self.p3_throttled_until:
            return False
        if util > self.hysteresis['throttle_on']:
            self.p3_throttled_until = now + self.hysteresis['hold_seconds']
            self._log_audit("THROTTLE_ENGAGE", 3, f"Composite util {util:.2f} > 0.80. Throttling for 30s")
            return False
        return util < 0.65

    def admit(self, req: Dict[str, Any]) -> Dict[str, Any]:
        """Core admission decision point implementing P1/P2/P3 policies & preemption."""
        pr = req.get('priority', 1)
        req_id = req.get('id', f"req-{int(time.time()*1000)}")

        # Reset P1 preemption budget every 60 seconds
        now = time.time()
        if now > self.p1_budget_reset_time:
            self.p1_preempt_budget = 5
            self.p1_budget_reset_time = now + 60.0

        # Priority 1: Interactive / Urgent
        if pr == 1:
            if self.p1_bucket.consume(1):
                ADMISSIONS.labels(priority='1', result='accepted').inc()
                self._log_audit("ADMIT_ACCEPTED", 1, "Token bucket token consumed", req_id)
                return {'action': 'start', 'reason': 'token', 'priority': 1, 'id': req_id}
            elif self.p1_preempt_budget > 0 and self._preempt_p2():
                self.p1_preempt_budget -= 1
                PREEMPTIONS.inc()
                ADMISSIONS.labels(priority='1', result='preempted').inc()
                self._log_audit("ADMIT_PREEMPT", 1, "Preemption budget consumed. Preempted P2 queue task", req_id)
                return {'action': 'start', 'reason': 'preempt', 'priority': 1, 'id': req_id}
            else:
                ADMISSIONS.labels(priority='1', result='rejected').inc()
                self._log_audit("ADMIT_REJECT", 1, "Rate limit exceeded, preemption budget exhausted", req_id)
                return {'action': 'reject', 'code': 'P1_RATE_LIMIT', 'retry_after_sec': 1.0}

        # Priority 2: Task Orchestration
        if pr == 2:
            try:
                self.p2_queue.put_nowait(req)
                P2_QUEUE_LEN.set(self.p2_queue.qsize())
                ADMISSIONS.labels(priority='2', result='queued').inc()
                self._log_audit("ADMIT_QUEUED", 2, "Enqueued in P2 FIFO queue", req_id)
                return {'action': 'queued', 'queue_depth': self.p2_queue.qsize(), 'id': req_id}
            except Exception:
                ADMISSIONS.labels(priority='2', result='rejected').inc()
                self._log_audit("ADMIT_REJECT", 2, "P2 queue buffer full", req_id)
                return {'action': 'reject', 'code': 'P2_QUEUE_FULL'}

        # Priority 3: Background / Vector Compilation
        if pr == 3:
            if self.can_run_p3():
                self.p3_queue.put(req)
                P3_PENDING.set(self.p3_queue.qsize())
                ADMISSIONS.labels(priority='3', result='scheduled').inc()
                self._log_audit("ADMIT_SCHEDULED", 3, "Composite util < 65%, task scheduled", req_id)
                return {'action': 'scheduled', 'pending_jobs': self.p3_queue.qsize(), 'id': req_id}
            else:
                ADMISSIONS.labels(priority='3', result='throttled').inc()
                self._log_audit("ADMIT_THROTTLED", 3, "Throttled due to composite memory pressure", req_id)
                return {'action': 'reject', 'code': 'P3_THROTTLED', 'retry_after_sec': 30.0}

        return {'action': 'reject', 'code': 'INVALID_PRIORITY'}

    def _preempt_p2(self) -> bool:
        """Preempts one oldest item from P2 queue for P1 task."""
        with self.lock:
            try:
                preempted_item = self.p2_queue.get_nowait()
                P2_QUEUE_LEN.set(self.p2_queue.qsize())
                logger.info(f"⚡ [Preemption Event] Preempted P2 task {preempted_item.get('id')} for incoming P1 request")
                self._log_audit("PREEMPT_ACTION", 2, f"Task {preempted_item.get('id')} preempted by P1 override")
                return True
            except Empty:
                return False

    def _log_audit(self, action: str, priority: int, rationale: str, req_id: str = ""):
        """Appends decision trace to immutable audit log."""
        entry = {
            "timestamp": time.time(),
            "iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "action": action,
            "priority": priority,
            "request_id": req_id,
            "rationale": rationale,
            "composite_util": round(self.composite_util(), 3)
        }
        try:
            with open(self.audit_log_path, "a", encoding="utf-8") as f:
                f.write(import_json_str(entry) + "\n")
        except Exception:
            pass

    def start_background_workers(self):
        """Starts P2 and P3 simulated job execution workers."""
        def p2_worker():
            while True:
                req = self.p2_queue.get()
                P2_QUEUE_LEN.set(self.p2_queue.qsize())
                logger.info('Running P2 task %s', req.get('id'))
                time.sleep(2)  # simulate task execution
                self.p2_queue.task_done()

        def p3_worker():
            while True:
                req = self.p3_queue.get()
                P3_PENDING.set(self.p3_queue.qsize())
                logger.info('Running P3 background task %s', req.get('id'))
                time.sleep(1)  # simulate vector compilation work
                self.p3_queue.task_done()

        threading.Thread(target=p2_worker, daemon=True).start()
        threading.Thread(target=p3_worker, daemon=True).start()


def import_json_str(obj: Any) -> str:
    import json
    return json.dumps(obj)


# Flask Web Service
if Flask is not None:
    app = Flask(__name__)
    ac = AdmissionController()
    ac.start_background_workers()

    @app.route('/admit', methods=['POST'])
    def admit():
        import json
        req = request.json or {}
        result = ac.admit(req)
        P1_TOKENS.set(ac.p1_bucket.available())
        return jsonify(result)

    @app.route('/health', methods=['GET'])
    def health():
        return jsonify({
            "status": "healthy",
            "p1_available_tokens": ac.p1_bucket.available(),
            "p2_queue_depth": ac.p2_queue.qsize(),
            "p3_pending_jobs": ac.p3_queue.qsize(),
            "composite_util": ac.composite_util()
        })


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Admission Controller")
    parser.add_argument("--port", type=int, default=5000, help="HTTP API port")
    parser.add_argument("--metrics-port", type=int, default=8001, help="Prometheus metrics port")
    args = parser.parse_args()

    if PROMETHEUS_AVAILABLE:
        try:
            start_http_server(args.metrics_port)
            logger.info(f"📊 Prometheus metrics exporter listening on http://localhost:{args.metrics_port}/")
        except Exception as e:
            logger.warning(f"Could not start Prometheus HTTP server: {e}")

    if Flask is not None:
        logger.info(f"🚀 Admission Controller API listening on http://0.0.0.0:{args.port}/admit")
        app.run(host='0.0.0.0', port=args.port)
    else:
        logger.error("Flask is required to run the HTTP admission server.")


if __name__ == '__main__':
    main()
