#!/bin/bash
set -e

echo "==========================================="
echo "   ABC-Bench Remote Execution Wrapper      "
echo "==========================================="

if [[ -z "$DOCKER_HOST" ]]; then
    echo "ERROR: DOCKER_HOST environment variable is NOT set!"
    echo ""
    echo "Running terminal-bench locally on this Mac will cause Docker to crash or freeze the system."
    echo "You MUST route Docker execution to a Free-Tier Cloud Sandbox (Codespaces, Gitpod, or a VPS)."
    echo ""
    echo "Example for GitHub Codespaces:"
    echo "  export DOCKER_HOST=\"ssh://codespace.your-codespace-name\""
    echo ""
    echo "Please check FREE_TIER_SANDBOXES.md for setup instructions."
    exit 1
fi

echo "[+] DOCKER_HOST is set to: $DOCKER_HOST"
echo "[+] Validating Docker connection to remote host..."

# Quick check if docker is accessible
if ! docker ps > /dev/null 2>&1; then
    echo "ERROR: Could not connect to remote Docker daemon at $DOCKER_HOST."
    echo "Please ensure SSH keys are configured and the remote sandbox is running."
    exit 1
fi

echo "[+] Remote Docker daemon connected successfully!"
echo "[+] Activating tb-env..."
source /Users/adarrsh/workspace/tb-env/bin/activate

echo "[+] Launching terminal-bench via custom_nanobot_adapter..."
tb run \
  --dataset-path /Users/adarrsh/workspace/ABC-Bench-Dataset \
  --agent-import-path custom_nanobot_adapter:NanobotAgent \
  --n-attempts 1 \
  --global-agent-timeout-sec 600 \
  --n-concurrent 1

echo "[+] Benchmark run finished."
