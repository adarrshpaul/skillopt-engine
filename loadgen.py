"""
Synthetic Load Generator for Heterogeneous Model & Admission Testing
===================================================================
Generates high-concurrency burst traffic to validate:
- Admission controller token bucket rate-limiting
- Priority 1 preemption and Priority 2 queue backpressure
- Priority 3 hysteresis throttling under simulated noisy-neighbor loads
"""

import sys
import time
import uuid
import json
import argparse
import urllib.request
import urllib.error

def run_loadgen(qps: float = 20.0, duration_sec: int = 60, priority: int = 2, target_url: str = "http://localhost:5000/admit"):
    end_time = time.time() + duration_sec
    interval = 1.0 / qps
    requests_sent = 0
    accepted = 0
    rejected = 0
    preempted = 0
    errors = 0

    print(f"\n🚀 [LoadGen Started] Target: {target_url} | QPS: {qps} | Priority: P{priority} | Duration: {duration_sec}s")
    start_t = time.time()

    while time.time() < end_time:
        payload = {
            'id': f"load-{str(uuid.uuid4())[:8]}",
            'priority': priority,
            'timestamp': time.time()
        }
        
        try:
            req_bytes = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(target_url, data=req_bytes, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=2.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                action = data.get("action", "unknown")
                reason = data.get("reason", "")
                
                if action in ("start", "scheduled", "queued"):
                    accepted += 1
                    if reason == "preempt":
                        preempted += 1
                elif action == "reject":
                    rejected += 1
        except Exception as e:
            errors += 1

        requests_sent += 1
        time.sleep(interval)

    total_time = time.time() - start_t
    print(f"\n📊 [LoadGen Completed in {total_time:.2f}s]")
    print(f"   Total Requests Sent: {requests_sent}")
    print(f"   Accepted / Scheduled: {accepted} (Preemptions: {preempted})")
    print(f"   Rejected / Throttled: {rejected}")
    print(f"   Network Errors:       {errors}")
    print(f"   Achieved Throughput:  {requests_sent / total_time:.1f} req/s\n")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Synthetic Load Generator")
    parser.add_argument("--qps", type=float, default=20.0, help="Target Queries Per Second")
    parser.add_argument("--duration", type=int, default=10, help="Test duration in seconds")
    parser.add_argument("--priority", type=int, default=2, help="Request priority tier (1, 2, or 3)")
    parser.add_argument("--url", type=str, default="http://localhost:5000/admit", help="Admission URL")
    args = parser.parse_args()

    run_loadgen(qps=args.qps, duration_sec=args.duration, priority=args.priority, target_url=args.url)
