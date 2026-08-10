"""Central Test Runner for SkillOpt QA Harness."""
import os
import sys
import psutil
import subprocess
import time
import json
import threading
import urllib.request
from typing import Dict, Any

class MemoryTracker:
    def __init__(self):
        self.ling_peak_rss = 0
        self.ornith_peak_rss = 0
        self.overlap_detected = False
        self.max_api_size = 0
        self.initial_swap = self._get_swap_usage()
        self.initial_wired = self._get_wired_pages()
        self.initial_compressor = self._get_compressor_pages()
        self.max_pressure = self._get_pressure_level()
        self.peak_compressor = self.initial_compressor
        self.running = False
        self.thread = None

    def _get_compressor_pages(self) -> int:
        """Returns macOS pages occupied by compressor."""
        try:
            output = subprocess.check_output(["vm_stat"], text=True)
            for line in output.splitlines():
                if "Pages occupied by compressor" in line:
                    return int(line.split(":")[1].strip().strip("."))
        except Exception:
            return 0
        return 0

    def _get_swap_usage(self) -> int:
        """Returns macOS pages swapped out (from vm_stat)."""
        try:
            output = subprocess.check_output(["vm_stat"], text=True)
            for line in output.splitlines():
                if "Pages swapped out" in line:
                    return int(line.split(":")[1].strip().strip("."))
        except Exception:
            return 0
        return 0

    def _get_wired_pages(self) -> int:
        """Returns macOS pages wired down."""
        try:
            output = subprocess.check_output(["vm_stat"], text=True)
            for line in output.splitlines():
                if "Pages wired down" in line:
                    return int(line.split(":")[1].strip().strip("."))
        except Exception:
            return 0
        return 0

    def _get_pressure_level(self) -> str:
        """Returns macOS memory pressure level."""
        try:
            output = subprocess.check_output(["sysctl", "kern.memorystatus_vm_pressure_level"], text=True)
            return output.split(":")[1].strip()
        except Exception:
            return "unknown"

    def _get_ollama_memory(self) -> int:
        """Returns actual RSS of Ollama daemon with /api/ps as sanity check."""
        try:
            # 1. Ground truth: psutil RSS
            output = subprocess.check_output(["pgrep", "-i", "ollama"], text=True)
            ollama_pids = [int(p.strip()) for p in output.splitlines() if p.strip()]
            
            actual_rss = 0
            for pid in ollama_pids:
                try:
                    proc = psutil.Process(pid)
                    actual_rss += proc.memory_info().rss
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            
            # 2. Sanity check: /api/ps reported size
            try:
                req = urllib.request.Request("http://localhost:11434/api/ps")
                with urllib.request.urlopen(req, timeout=2) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    api_size = sum(m.get("size", 0) for m in data.get("models", []))
                    self.max_api_size = max(self.max_api_size, api_size)
            except Exception:
                pass
                
            return actual_rss
        except Exception:
            return 0

    def _poll_memory(self, pids: list[int]):
        while self.running:
            runner_rss = 0
            for pid in pids:
                try:
                    proc = psutil.Process(pid)
                    runner_rss += proc.memory_info().rss
                    for child in proc.children(recursive=True):
                        try:
                            runner_rss += child.memory_info().rss
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            continue
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            
            # Actual Ollama daemon RSS
            ollama_rss = self._get_ollama_memory()
            
            # Per-phase peaks
            self.ling_peak_rss = max(self.ling_peak_rss, runner_rss)
            self.ornith_peak_rss = max(self.ornith_peak_rss, ollama_rss)
            
            # Overlap detection (if both are > 1GB simultaneously)
            if runner_rss > 1024**3 and ollama_rss > 1024**3:
                self.overlap_detected = True
            
            pressure = self._get_pressure_level()
            if pressure != "unknown":
                if pressure in ("warn", "critical"):
                    print(f"\n🚨 [CIRCUIT BREAKER] macOS Memory Pressure hit '{pressure.upper()}'. Aborting test to prevent kernel panic!", flush=True)
                    for pid in pids:
                        try:
                            import signal
                            os.killpg(os.getpgid(pid), signal.SIGKILL)
                        except Exception:
                            pass
                    self.max_pressure = pressure
                    self.running = False
                    break
                elif self.max_pressure != "critical":
                    if pressure == "critical" or (pressure == "warn" and self.max_pressure == "normal"):
                        self.max_pressure = pressure
                        
            cur_compressor = self._get_compressor_pages()
            self.peak_compressor = max(self.peak_compressor, cur_compressor)

            time.sleep(0.5)

    def start(self, pids: list[int]):
        self.running = True
        self.thread = threading.Thread(target=self._poll_memory, args=(pids,), daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join()

    def get_metrics(self) -> Dict[str, Any]:
        current_swap = self._get_swap_usage()
        current_wired = self._get_wired_pages()
        return {
            "ling_peak_rss_mb": self.ling_peak_rss / (1024 * 1024),
            "ornith_peak_rss_mb": self.ornith_peak_rss / (1024 * 1024),
            "overlap_detected": self.overlap_detected,
            "max_api_size_mb": self.max_api_size / (1024 * 1024),
            "swap_delta_pages": max(0, current_swap - self.initial_swap),
            "wired_delta_pages": current_wired - self.initial_wired,
            "max_pressure_level": self.max_pressure,
            "peak_compressor_pages": self.peak_compressor,
            "initial_compressor_pages": self.initial_compressor
        }

def run_suite():
    print("🚀 Starting SkillOpt QA Harness...")
    tracker = MemoryTracker()
    tracker.start([os.getpid()])
    
    # Run tests using pytest
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "autoqa/tests/", "-v", "--tb=short"],
        cwd=os.path.abspath(os.path.join(os.path.dirname(__file__), "..")),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True
    )
    
    tracker.stop()
    metrics = tracker.get_metrics()
    
    status = "PASSED" if result.returncode == 0 else "FAILED"
    
    report = {
        "timestamp": time.time(),
        "suite_status": status,
        "metrics": metrics,
        "pytest_output": result.stdout
    }
    
    os.makedirs("autoqa/reports", exist_ok=True)
    with open("autoqa/reports/qa_report.json", "w") as f:
        json.dump(report, f, indent=4)
        
    print(f"\n✅ QA Suite Complete. Status: {status}")
    print(f"📊 Ling-mini Peak RSS: {metrics['ling_peak_rss_mb']:.2f} MB")
    print(f"📊 Ornith Peak RSS: {metrics['ornith_peak_rss_mb']:.2f} MB (API reported: {metrics['max_api_size_mb']:.2f} MB)")
    print(f"🚨 Concurrent Overlap Detected: {metrics['overlap_detected']}")
    print(f"🔄 Swap Delta: {metrics['swap_delta_pages']} pages")
    print(f"📌 Wired Delta: {metrics['wired_delta_pages']} pages")
    print(f"🚨 Max Pressure: {metrics['max_pressure_level']}")
    print(f"🗜️ Peak Compressor Pages: {metrics['peak_compressor_pages']} (Start: {metrics['initial_compressor_pages']})")
    
    if metrics['overlap_detected']:
        print("🛑 FATAL: Engine Swap Failed! Concurrent memory overlap detected.", flush=True)
        return 1
    
    return result.returncode

if __name__ == "__main__":
    sys.exit(run_suite())
