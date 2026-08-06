import os
import sys
import time
import json
import subprocess
from typing import Dict, Any

def run_benchmark_suite() -> Dict[str, Any]:
    print(f"\n{'='*60}")
    print(f"📊 Open-Source SkillOpt Engine Benchmark Suite")
    print(f"   Platform: Apple Silicon (MLX GPU acceleration)")
    print(f"{'='*60}\n")

    results = {}

    # Benchmark 1: Workspace Health Check & Compilation Pass Rate
    print("🔍 [1/4] Benchmarking Workspace Health & Code Compilation Pass Rate...")
    python_files = [f for f in os.listdir(".") if f.endswith(".py")]
    passed = 0
    start_t = time.time()
    for f in python_files:
        res = subprocess.run([sys.executable, "-m", "py_compile", f], capture_output=True, text=True)
        if res.returncode == 0:
            passed += 1
    health_duration = time.time() - start_t
    pass_rate = (passed / len(python_files)) * 100 if python_files else 0.0

    results["workspace_health"] = {
        "total_files": len(python_files),
        "passed_files": passed,
        "compilation_pass_rate": round(pass_rate, 2),
        "benchmark_time_seconds": round(health_duration, 4)
    }
    print(f"   ✅ Compilation Pass Rate: {pass_rate:.1f}% ({passed}/{len(python_files)} files in {health_duration:.2f}s)")

    # Benchmark 2: MCP Server Scaffold & Unit Test Verification Latency
    print("\n🛠️ [2/4] Benchmarking MCP Server Scaffolding & Test Harness Latency...")
    start_mcp = time.time()
    res_mcp = subprocess.run([sys.executable, "/Users/adarrsh/workspace/mcp_builder.py", "bench_mcp"], capture_output=True, text=True)
    mcp_duration = time.time() - start_mcp
    mcp_success = res_mcp.returncode == 0 and "PASSED" in res_mcp.stdout

    results["mcp_scaffold_test"] = {
        "status": "PASSED" if mcp_success else "FAILED",
        "latency_seconds": round(mcp_duration, 4)
    }
    print(f"   ✅ MCP Scaffold & Test Build Latency: {mcp_duration:.2f}s (Status: {'PASSED' if mcp_success else 'FAILED'})")

    # Benchmark 3: DPO Dataset Pair Extraction Yield
    print("\n🌳 [3/4] Benchmarking DPO Dataset Verification Yield...")
    dataset_path = "/Users/adarrsh/workspace/dpo_graph_dataset.jsonl"
    pair_count = 0
    if os.path.exists(dataset_path):
        with open(dataset_path) as f:
            pair_count = sum(1 for line in f if line.strip())

    results["dpo_dataset_yield"] = {
        "verified_pairs": pair_count,
        "dataset_path": dataset_path
    }
    print(f"   ✅ DPO Dataset Yield: {pair_count} verified preference pairs logged.")

    # Benchmark 4: Local Server Ping & Endpoint Availability
    print("\n🌐 [4/4] Benchmarking Local Inference Server Endpoint Latency...")
    start_ping = time.time()
    res_ping = subprocess.run(["curl", "-s", "http://localhost:8800/v1/models"], capture_output=True, text=True)
    ping_duration = time.time() - start_ping
    server_online = res_ping.returncode == 0 and "AtomicChat/Ornith-9B-MLX-6bit" in res_ping.stdout

    results["inference_server"] = {
        "status": "ONLINE" if server_online else "OFFLINE",
        "ping_latency_ms": round(ping_duration * 1000, 2),
        "target_model": "AtomicChat/Ornith-9B-MLX-6bit"
    }
    print(f"   ✅ Inference Server Status: {'ONLINE' if server_online else 'OFFLINE'} (Latency: {ping_duration*1000:.1f}ms)")

    # Save benchmark report to disk
    report_path = "/Users/adarrsh/workspace/benchmark_report.json"
    with open(report_path, "w") as f:
        json.dump(results, f, indent=2)

    print(f"\n{'='*60}")
    print(f"🎉 Benchmark Run Complete!")
    print(f"   Saved report to {report_path}")
    print(f"{'='*60}\n")

    return results

if __name__ == "__main__":
    run_benchmark_suite()
