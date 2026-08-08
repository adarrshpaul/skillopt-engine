#!/usr/bin/env bash
# Stop the two small mlx_lm.server processes (+ any leftover fleet/gateway).
set -euo pipefail

LOGDIR="/Users/adarrsh/workspace/logs/mlx_servers"

if [[ -d "$LOGDIR" ]]; then
  for pidfile in "$LOGDIR"/*.pid; do
    [[ -f "$pidfile" ]] || continue
    pid=$(cat "$pidfile" 2>/dev/null || true)
    if [[ -n "${pid:-}" ]] && kill -0 "$pid" 2>/dev/null; then
      echo "Stopping pid $pid ($(basename "$pidfile"))"
      kill "$pid" 2>/dev/null || true
    fi
    rm -f "$pidfile"
  done
fi

pkill -f "mlx_lm.server" 2>/dev/null || true
pkill -f "mlx_fleet_gateway.py" 2>/dev/null || true
echo "Stopped small-model fleet."
