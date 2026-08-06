#!/usr/bin/env zsh
# =============================================================================
# sync_from_drive.sh — Pull GGUF models from Google Drive to local
# =============================================================================
# Prerequisites:
#   brew install rclone
#   rclone config  →  add a remote named "gdrive" (follow interactive wizard)
#
# Usage:
#   ./sync_from_drive.sh              # sync all models
#   ./sync_from_drive.sh mymodel.gguf # sync specific file
# =============================================================================

set -euo pipefail

REMOTE="gdrive"
REMOTE_DIR="ollama-models"
LOCAL_DIR="$HOME/workspace/models"

GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
RESET='\033[0m'

mkdir -p "$LOCAL_DIR"

# Check rclone is installed
if ! command -v rclone &>/dev/null; then
  echo "${YELLOW}[sync] rclone not found. Install it:${RESET}"
  echo "  brew install rclone"
  echo "  rclone config   # add 'gdrive' remote for Google Drive"
  exit 1
fi

# Check remote is configured
if ! rclone listremotes | grep -q "^${REMOTE}:"; then
  echo "${YELLOW}[sync] Remote '${REMOTE}' not configured. Run:${RESET}"
  echo "  rclone config"
  echo "  Then add a remote named '${REMOTE}' pointing to Google Drive"
  exit 1
fi

if [[ -n "${1:-}" ]]; then
  # Sync specific file
  echo "${CYAN}[sync]${RESET} Downloading $1 from Drive..."
  rclone copy "${REMOTE}:${REMOTE_DIR}/$1" "$LOCAL_DIR/" --progress
else
  # Sync all .gguf files
  echo "${CYAN}[sync]${RESET} Syncing all models from Drive → $LOCAL_DIR/"
  rclone copy "${REMOTE}:${REMOTE_DIR}/" "$LOCAL_DIR/" \
    --include "*.gguf" \
    --progress
fi

echo ""
echo "${GREEN}[sync] ✅ Done. Models in $LOCAL_DIR/:${RESET}"
ls -lh "$LOCAL_DIR/"*.gguf 2>/dev/null || echo "  (no .gguf files yet)"
