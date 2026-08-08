"""
Latency Probe & SLO Compliance Verification Engine
=================================================
Probes Priority 1 interactive endpoint at specified QPS,
calculates P50, P95, and P99 latency percentiles, and asserts SLO compliance.
"""

import sys
import time
import json
import argparse
import urllib.request
import urllib.error
from typing import List

def run_latency_probe(qps: float = 5.0, duration_sec: int = 30, target_url: str = "http://localhost:5000/admit", slo_p95_ms: float = 350.0):
    end_time = time.time() + duration_sec
    interval = 1.0 / qps
    latencies: List[float] = []
    successes = 0
    failures = 0

    print(f"\n🔍 [Latency Probe Started] Target: {target_url} | QPS: {qps} | Target P95 SLO: {slo_p95_ms}ms")
    start_t = time.time()

    while time.time() < end_time:
        t0 = time.time()
        payload = {'id': 'probe-p1', 'priority': 1, 'timestamp': t0}
        
        try:
            req_bytes = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(target_url, data=req_bytes, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=2.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                duration_ms = (time.time() - t0) * 1000.0
                latencies.append(duration_ms)
                if data.get("action") == "start":
                    successes += 1
                else:
                    failures += 1
        except Exception:
            duration_ms = (time.time() - t0) * 1000.0
            latencies.append(duration_ms)
            failures += 1

        time.sleep(interval)

    total_probes = len(latencies)
    if not latencies:
        print("❌ No successful probes recorded.")
        return

    sorted_lats = sorted(latencies)
    p50 = sorted_lats[int(0.50 * total_probes)]
    p90 = sorted_lats[int(0.90 * total_probes)]
    p95 = sorted_lats[int(0.95 * total_probes)]
    p99 = sorted_lats[int(0.99 * total_probes)]
    min_lat = sorted_lats[0]
    max_lat = sorted_lats[-1]

    slo_met = p95 <= slo_p95_ms
    slo_badge = "✅ PASSED" if slo_met else "❌ BREACHED"

    print(f"\n📊 [Latency Probe Report — {time.time() - start_t:.1f}s Duration]")
    print(f"   Total Probes:       {total_probes} (Success: {successes}, Rejections: {failures})")
    print(f"   Min / Max Latency:  {min_lat:.1f}ms / {max_lat:.1f}ms")
    print(f"   P50 (Median):       {p50:.1f}ms")
    print(f"   P90:                {p90:.1f}ms")
    print(f"   P95:                {p95:.1f}ms (Target: <= {slo_p95_ms}ms) -> {slo_badge}")
    print(f"   P99:                {p99:.1f}ms")
    print(f"   Availability Rate:  {(successes / total_probes) * 100:.1f}%\n")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Latency Probe and SLO Verifier")
    parser.add_argument("--qps", type=float, default=5.0, help="Queries per second")
    parser.add_argument("--duration", type=int, default=15, help="Test duration in seconds")
    parser.add_argument("--url", type=str, default="http://localhost:5000/admit", help="Target URL")
    parser.add_argument("--slo", type=float, default=350.0, help="P95 SLO threshold in ms")
    args = parser.parse_args()

    run_latency_probe(qps=args.qps, duration_sec=args.duration, target_url=args.url, slo_p95_ms=args.slo)
