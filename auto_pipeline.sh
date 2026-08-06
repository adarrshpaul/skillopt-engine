#!/usr/bin/env zsh
# =============================================================================
# auto_pipeline.sh — Automated End-to-End Local Model Pipeline
# =============================================================================

set -euo pipefail

GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
RESET='\033[0m'

WORKSPACE_DIR="$HOME/workspace"
MACHINE_DIR="$HOME/machine"
MODEL_NAME="ix-copilot-q4"

echo "${CYAN}[automation]${RESET} Starting End-to-End Model Pipeline..."

# 1. Sync weights from Drive
echo "${CYAN}[automation]${RESET} Step 1: Checking/Syncing model weights..."
cd "$WORKSPACE_DIR/scripts"
if [[ -x "./sync_from_drive.sh" ]]; then
    ./sync_from_drive.sh || true
else
    echo "${YELLOW}[automation] sync_from_drive.sh not found or not executable. Skipping.${RESET}"
fi

# Verify weights exist before proceeding
if [[ ! -f "$WORKSPACE_DIR/models/unsloth.F16.gguf" ]]; then
    echo "${YELLOW}[automation] Warning: Custom model weights not found at $WORKSPACE_DIR/models/unsloth.F16.gguf!${RESET}"
    echo "${CYAN}[automation]${RESET} Falling back to pulling a lightweight model from Ollama registry for testing..."
    if command -v ollama &>/dev/null; then
        ollama pull qwen2.5:0.5b
        ollama cp qwen2.5:0.5b unsloth
        echo "${GREEN}[automation] Fallback model configured as 'unsloth'.${RESET}"
    else
        echo "${RED}[automation] Fatal: Ollama not found. Aborting.${RESET}"
        exit 1
    fi
else
    # 2. Create the Ollama Model from GGUF
    echo "${CYAN}[automation]${RESET} Step 2: Generating Modelfile & Building Ollama model..."
    if [[ -x "./create_ollama_model.sh" ]]; then
        ./create_ollama_model.sh
    else
        echo "${RED}[automation] create_ollama_model.sh not found. Aborting pipeline.${RESET}"
        exit 1
    fi
fi

# 3. Ensure Ollama is running
echo "${CYAN}[automation]${RESET} Step 3: Verifying Ollama Engine..."
if ! curl -s http://localhost:11434/api/tags >/dev/null; then
    echo "${YELLOW}[automation] Ollama is not running. Starting in background...${RESET}"
    OLLAMA_MODELS="$WORKSPACE_DIR/models" ollama serve > /tmp/ollama-auto.log 2>&1 &
    sleep 3
fi

# 4. Run automated test inference
echo "${CYAN}[automation]${RESET} Step 4: Testing Model Inference..."
if [[ -x "./test_ollama.sh" ]]; then
    ./test_ollama.sh
else
    # Fallback to direct curl test
    echo "Sending health check prompt to $MODEL_NAME..."
    curl -s http://localhost:11434/api/generate -d "{
      \"model\": \"$MODEL_NAME\",
      \"prompt\": \"Write a single sentence saying hello world.\",
      \"stream\": false
    }" | grep -q "response" && echo "${GREEN}Model is responsive!${RESET}" || echo "${RED}Model inference failed!${RESET}"
fi

echo "${GREEN}[automation] ✅ End-to-End Pipeline Complete.${RESET}"
