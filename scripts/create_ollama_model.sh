#!/usr/bin/env zsh
# =============================================================================
# create_ollama_model.sh — Register a GGUF file with Ollama
# =============================================================================
# Usage:
#   ./create_ollama_model.sh <model-name> <gguf-filename>
#   ./create_ollama_model.sh phi3-mini phi3-mini-q4_k_m.gguf
#   ./create_ollama_model.sh my-model my-finetuned-model-q4_k_m.gguf "You are a helpful coding assistant."
#
# The GGUF file must be in ~/workspace/models/
# =============================================================================

set -euo pipefail

MODEL_NAME="${1:-}"
GGUF_FILE="${2:-}"
SYSTEM_PROMPT="${3:-You are a helpful AI assistant.}"
MODELS_DIR="$HOME/workspace/models"

GREEN='\033[0;32m'
CYAN='\033[0;36m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
RESET='\033[0m'

if [[ -z "$MODEL_NAME" || -z "$GGUF_FILE" ]]; then
  echo "${YELLOW}Usage:${RESET} $0 <model-name> <gguf-filename> [system-prompt]"
  echo ""
  echo "Available GGUF files in $MODELS_DIR/:"
  ls -lh "$MODELS_DIR/"*.gguf 2>/dev/null || echo "  (none — run sync_from_drive.sh first)"
  exit 1
fi

GGUF_PATH="$MODELS_DIR/$GGUF_FILE"
if [[ ! -f "$GGUF_PATH" ]]; then
  echo "${RED}[create] ✘ File not found: $GGUF_PATH${RESET}"
  echo "Available files:"
  ls "$MODELS_DIR/"*.gguf 2>/dev/null || echo "  (none)"
  exit 1
fi

# Check Ollama is running
if ! curl -sf http://localhost:11434/api/tags &>/dev/null; then
  echo "${YELLOW}[create] Ollama is not running. Starting...${RESET}"
  ollama serve &>/dev/null &
  sleep 2
fi

# Generate Modelfile
MODELFILE="$MODELS_DIR/Modelfile.${MODEL_NAME}"
cat > "$MODELFILE" <<EOF
FROM $GGUF_PATH

SYSTEM """${SYSTEM_PROMPT}"""

PARAMETER temperature 0.7
PARAMETER top_p 0.9
PARAMETER top_k 40
PARAMETER num_ctx 4096
EOF

echo "${CYAN}[create]${RESET} Modelfile written to $MODELFILE"
echo "${CYAN}[create]${RESET} Registering with Ollama..."

ollama create "$MODEL_NAME" -f "$MODELFILE"

echo ""
echo "${GREEN}[create] ✅ Model '$MODEL_NAME' registered with Ollama!${RESET}"
echo ""
echo "  Test it:    ollama run $MODEL_NAME"
echo "  API call:   curl http://localhost:11434/api/generate -d '{\"model\":\"$MODEL_NAME\",\"prompt\":\"Hello!\"}'"
echo ""
echo "Current Ollama models:"
ollama list
