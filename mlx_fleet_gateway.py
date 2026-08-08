#!/usr/bin/env python3
"""
MLX Fleet Gateway — 4 UI ports that stay alive on 16GB Apple Silicon.

Problem: loading fused-gemma + gemma-2-9b + Ornith-9B concurrently OOMs a 16GB Mac.
Solution:
  - :8802 always runs the compact Nanbeige/Qwen2.5-0.5B process
  - :8801 / :8803 / :8804 are thin OpenAI-compatible proxies that hot-swap a
    single shared heavy mlx_lm.server worker on :8799

So every UI card has its own port, and the large models never reside in memory
at the same time.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

PYTHON = os.environ.get("MLX_PYTHON", "/Users/adarrsh/workspace/ml-env-311/bin/python3.11")
LOGDIR = "/Users/adarrsh/workspace/logs/mlx_servers"
INTERNAL_PORT = 8799
INTERNAL_URL = f"http://127.0.0.1:{INTERNAL_PORT}/v1"

# UI key → (listen_port, model_id, mode)
# mode: "always" = dedicated process; "swap" = shared heavy worker
FLEET = {
    "ling-3.0-flash": {
        "port": 8801,
        "model": "/Users/adarrsh/workspace/models/fused-gemma",
        "mode": "swap",
        "name": "ling",
    },
    "nanbeige-3b": {
        "port": 8802,
        "model": "Qwen/Qwen2.5-0.5B-Instruct",
        "mode": "always",
        "name": "nanbeige",
    },
    "gemma-4-12b": {
        "port": 8803,
        "model": "mlx-community/gemma-2-9b-it-4bit",
        "mode": "swap",
        "name": "gemma",
    },
    "ornith-9b": {
        "port": 8800,
        "model": "AtomicChat/Ornith-9B-MLX-6bit",
        "mode": "swap",
        "name": "ornith",
    },
}

PORT_TO_SPEC = {spec["port"]: {**spec, "key": key} for key, spec in FLEET.items()}


class HeavySlot:
    """Single shared mlx_lm.server process for large models (hot-swapped)."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._proc: Optional[subprocess.Popen] = None
        self._active_model: Optional[str] = None
        self._active_name: Optional[str] = None

    def ensure(self, model_id: str, name: str) -> None:
        with self._lock:
            if self._proc and self._proc.poll() is None and self._active_model == model_id:
                if self._healthy(INTERNAL_PORT):
                    return
            self._stop()
            self._start(model_id, name)

    def _start(self, model_id: str, name: str) -> None:
        os.makedirs(LOGDIR, exist_ok=True)
        logfile = open(f"{LOGDIR}/heavy_worker.log", "a", buffering=1)
        cmd = [
            PYTHON, "-m", "mlx_lm.server",
            "--model", model_id,
            "--host", "127.0.0.1",
            "--port", str(INTERNAL_PORT),
        ]
        print(f"[fleet] loading heavy worker '{name}' → {model_id} on :{INTERNAL_PORT}", flush=True)
        self._proc = subprocess.Popen(cmd, stdout=logfile, stderr=subprocess.STDOUT)
        self._active_model = model_id
        self._active_name = name
        deadline = time.time() + 180
        while time.time() < deadline:
            if self._proc.poll() is not None:
                raise RuntimeError(f"heavy worker '{name}' exited early (code={self._proc.returncode})")
            if self._healthy(INTERNAL_PORT):
                print(f"[fleet] heavy worker '{name}' ready", flush=True)
                return
            time.sleep(1)
        raise TimeoutError(f"heavy worker '{name}' failed to become ready in 180s")

    def _stop(self) -> None:
        if self._proc and self._proc.poll() is None:
            print(f"[fleet] unloading heavy worker '{self._active_name}'", flush=True)
            self._proc.send_signal(signal.SIGTERM)
            try:
                self._proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                self._proc.kill()
        self._proc = None
        self._active_model = None
        self._active_name = None
        # Ensure port is free
        subprocess.run(["pkill", "-f", f"mlx_lm.server.*--port {INTERNAL_PORT}"], check=False)

    @staticmethod
    def _healthy(port: int) -> bool:
        try:
            with urlopen(f"http://127.0.0.1:{port}/v1/models", timeout=2) as resp:
                return resp.status == 200
        except Exception:
            return False


HEAVY = HeavySlot()
ALWAYS_PROCS: dict[int, subprocess.Popen] = {}


def start_always_on() -> None:
    os.makedirs(LOGDIR, exist_ok=True)
    for key, spec in FLEET.items():
        if spec["mode"] != "always":
            continue
        port = spec["port"]
        logfile = open(f"{LOGDIR}/{spec['name']}.log", "a", buffering=1)
        cmd = [
            PYTHON, "-m", "mlx_lm.server",
            "--model", spec["model"],
            "--host", "127.0.0.1",
            "--port", str(port),
        ]
        print(f"[fleet] starting always-on {key} on :{port}", flush=True)
        proc = subprocess.Popen(cmd, stdout=logfile, stderr=subprocess.STDOUT)
        ALWAYS_PROCS[port] = proc
        deadline = time.time() + 120
        while time.time() < deadline:
            if proc.poll() is not None:
                raise RuntimeError(f"always-on {key} exited early")
            try:
                with urlopen(f"http://127.0.0.1:{port}/v1/models", timeout=2) as resp:
                    if resp.status == 200:
                        print(f"[fleet] always-on {key} ready", flush=True)
                        break
            except Exception:
                time.sleep(1)
        else:
            raise TimeoutError(f"always-on {key} not ready")


def proxy_json(method: str, url: str, body: bytes, headers: dict) -> tuple[int, bytes, str]:
    req = Request(url, data=body if method != "GET" else None, headers=headers, method=method)
    try:
        with urlopen(req, timeout=180) as resp:
            return resp.status, resp.read(), resp.headers.get("Content-Type", "application/json")
    except HTTPError as e:
        return e.code, e.read(), "application/json"
    except URLError as e:
        return 502, json.dumps({"error": str(e)}).encode(), "application/json"


class FleetHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write("[proxy %s] %s\n" % (self.server.server_port, fmt % args))

    def _read_body(self) -> bytes:
        length = int(self.headers.get("Content-Length", 0))
        return self.rfile.read(length) if length else b""

    def _send(self, status: int, body: bytes, content_type: str = "application/json") -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

    def do_GET(self) -> None:
        port = self.server.server_port
        spec = PORT_TO_SPEC[port]
        if self.path.rstrip("/").endswith("/models") or self.path.startswith("/v1/models"):
            payload = {
                "object": "list",
                "data": [{
                    "id": spec["model"],
                    "object": "model",
                    "owned_by": "skillopt-fleet",
                    "port": port,
                    "ui_key": spec["key"],
                    "mode": spec["mode"],
                }],
            }
            self._send(200, json.dumps(payload).encode())
            return
        self._send(404, b'{"error":"not found"}')

    def do_POST(self) -> None:
        port = self.server.server_port
        spec = PORT_TO_SPEC[port]
        body = self._read_body()

        # Ensure correct backend is up
        if spec["mode"] == "always":
            upstream = f"http://127.0.0.1:{port}"
            # Direct process already listens on this port — should not happen for always
            # (gateway only binds swap ports). Defensive fallback:
            upstream = f"http://127.0.0.1:{port}"
            self._send(500, b'{"error":"always-on port should not be proxied"}')
            return

        try:
            HEAVY.ensure(spec["model"], spec["name"])
        except Exception as e:
            self._send(503, json.dumps({"error": f"failed to load {spec['name']}: {e}"}).encode())
            return

        # Force the model id in the payload so upstream accepts it
        try:
            data = json.loads(body.decode() or "{}")
        except Exception:
            data = {}
        data["model"] = spec["model"]
        body = json.dumps(data).encode()

        path = self.path if self.path.startswith("/") else f"/{self.path}"
        if not path.startswith("/v1/"):
            # normalize /chat/completions → /v1/chat/completions
            if path.startswith("/chat"):
                path = "/v1" + path
        url = f"{INTERNAL_URL}{path[3:] if path.startswith('/v1') else path}"
        # INTERNAL_URL already includes /v1
        if path.startswith("/v1/"):
            url = f"http://127.0.0.1:{INTERNAL_PORT}{path}"
        else:
            url = f"http://127.0.0.1:{INTERNAL_PORT}/v1{path}"

        headers = {"Content-Type": "application/json"}
        status, resp_body, ctype = proxy_json("POST", url, body, headers)
        self._send(status, resp_body, ctype)


def serve_port(port: int) -> None:
    httpd = ThreadingHTTPServer(("127.0.0.1", port), FleetHandler)
    print(f"[fleet] proxy listening on :{port} ({PORT_TO_SPEC[port]['key']})", flush=True)
    httpd.serve_forever()


def shutdown(*_args) -> None:
    print("[fleet] shutting down...", flush=True)
    HEAVY._stop()
    for proc in ALWAYS_PROCS.values():
        if proc.poll() is None:
            proc.send_signal(signal.SIGTERM)
    subprocess.run(["pkill", "-f", "mlx_lm.server"], check=False)
    sys.exit(0)


def main() -> None:
    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    # Clear any previous mlx servers
    subprocess.run(["pkill", "-f", "mlx_lm.server"], check=False)
    time.sleep(1)

    start_always_on()

    # Preload Ling (default UI card) into the heavy slot so first chat is fast
    ling = FLEET["ling-3.0-flash"]
    HEAVY.ensure(ling["model"], ling["name"])

    threads = []
    for key, spec in FLEET.items():
        if spec["mode"] != "swap":
            continue
        t = threading.Thread(target=serve_port, args=(spec["port"],), daemon=True)
        t.start()
        threads.append(t)

    print("[fleet] gateway ready — ports 8801/8803/8804 swap; 8802 always-on", flush=True)
    while True:
        time.sleep(3600)


if __name__ == "__main__":
    main()
