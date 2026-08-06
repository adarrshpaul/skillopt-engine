#!/usr/bin/env zsh
# =============================================================================
# test_ollama.sh — Smoke-test local Ollama API
# =============================================================================
# Usage:
#   ./test_ollama.sh                    # test default model (first in list)
#   ./test_ollama.sh phi3-mini          # test specific model
#   ./test_ollama.sh phi3-mini "Explain LoRA fine-tuning in 2 sentences"
# =============================================================================

set -euo pipefail

GREEN='\033[0;32m'
CYAN='\033[0;36m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BOLD='\033[1m'
RESET='\033[0m'

OLLAMA_URL="http://localhost:11434"

echo ""
echo "${BOLD}${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
echo "${BOLD}${CYAN}  🧪  Ollama Smoke Test                  ${RESET}"
echo "${BOLD}${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
echo ""

# Step 1: Check Ollama is running
echo "${CYAN}[test]${RESET} Checking Ollama at $OLLAMA_URL..."
if ! curl -sf "$OLLAMA_URL/api/tags" &>/dev/null; then
  echo "${RED}[test] ✘ Ollama not responding. Start it:${RESET}"
  echo "  ollama serve"
  exit 1
fi
echo "${GREEN}[test] ✔ Ollama is running${RESET}"

# Step 2: List models
echo ""
echo "${CYAN}[test]${RESET} Available models:"
ollama list
echo ""

# Step 3: Pick model
MODEL="${1:-$(ollama list | tail -n +2 | head -1 | awk '{print $1}')}"
PROMPT="${2:-Write a one-line Python function that returns the nth Fibonacci number.}"

if [[ -z "$MODEL" ]]; then
  echo "${RED}[test] ✘ No models found. Run create_ollama_model.sh first.${RESET}"
  exit 1
fi

echo "${CYAN}[test]${RESET} Testing model: ${BOLD}$MODEL${RESET}"
echo "${CYAN}[test]${RESET} Prompt: $PROMPT"
echo ""
echo "${YELLOW}─── Response ──────────────────────────────────────────${RESET}"

# Step 4: Call Ollama API (streaming)
curl -sf "$OLLAMA_URL/api/generate" \
  -d "{\"model\":\"$MODEL\",\"prompt\":\"$PROMPT\",\"stream\":false}" \
  | python3 -c "import sys,json; print(json.load(sys.stdin).get('response','(no response)'))"

echo ""
echo "${YELLOW}──────────────────────────────────────────────────────${RESET}"
echo ""
echo "${GREEN}[test] ✅ Smoke test passed!${RESET}"

# Step 5: Show stats
echo ""
echo "${CYAN}[test]${RESET} API endpoints:"
echo "  Generate:  POST $OLLAMA_URL/api/generate"
echo "  Chat:      POST $OLLAMA_URL/api/chat"
echo "  Embeddings: POST $OLLAMA_URL/api/embed"
echo "  Models:    GET  $OLLAMA_URL/api/tags"
