#!/usr/bin/env bash
# Start Ling + Nanbeige dedicated mlx_lm.server processes (ports 8801 + 8802).
set -euo pipefail

PYTHON="${MLX_PYTHON:-/Users/adarrsh/workspace/ml-env-311/bin/python3.11}"
LOGDIR="/Users/adarrsh/workspace/logs/mlx_servers"
HOST="127.0.0.1"
LING_MODEL="mlx-community/Ling-mini-2.0-4bit"
NANBEIGE_MODEL="mlx-community/Nanbeige4.1-3B-heretic-4bit"
ORNITH_MODEL="AtomicChat/Ornith-9B-MLX-6bit"
mkdir -p "$LOGDIR"

if [[ ! -x "$PYTHON" ]]; then
  echo "ERROR: MLX python not found at $PYTHON"
  exit 1
fi

pkill -f "mlx_lm.server" 2>/dev/null || true
pkill -f "mlx_fleet_gateway.py" 2>/dev/null || true
sleep 1

start_one() {
  local port="$1"
  local model="$2"
  local name="$3"
  local logfile="$LOGDIR/${name}.log"
  local pidfile="$LOGDIR/${name}.pid"

  echo "→ Starting $name on :$port ($model)"
  nohup "$PYTHON" -m mlx_lm.server \
    --model "$model" \
    --host "$HOST" \
    --port "$port" \
    >"$logfile" 2>&1 &
  echo $! >"$pidfile"
  echo "  pid=$(cat "$pidfile") log=$logfile"
}

# Nanbeige first (smaller ~2.2GB), then Ling-mini (~9GB), then Ornith (~9GB)
start_one 8802 "$NANBEIGE_MODEL" "nanbeige"
sleep 3
start_one 8801 "$LING_MODEL" "ling"
sleep 3
start_one 8800 "$ORNITH_MODEL" "ornith"

echo
echo "Waiting for /v1/models health (first download can take several minutes)..."
for port in 8800 8801 8802; do
  ok=0
  for i in $(seq 1 180); do
    if curl -sf "http://127.0.0.1:${port}/v1/models" >/dev/null 2>&1; then
      echo "  ✅ :${port} ready"
      ok=1
      break
    fi
    sleep 2
  done
  if [[ "$ok" -ne 1 ]]; then
    echo "  ❌ :${port} NOT ready — check $LOGDIR/*.log"
    exit 1
  fi
done

echo
lsof -nP -iTCP:8800 -iTCP:8801 -iTCP:8802 -sTCP:LISTEN 2>/dev/null || true
echo "Done. Ornith (:8800) + Ling (:8801) + Nanbeige (:8802) online."
