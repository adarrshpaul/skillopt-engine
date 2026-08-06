#!/usr/bin/env zsh
export PYTHONPATH="/Users/adarrsh/siemens-ix-mcp/src:/Users/adarrsh/siemens-ix-mcp"
export IX_KNOWLEDGE_ROOT="/Users/adarrsh/siemens-ix-mcp/knowledge"
export IX_SKILLS_ROOT="/Users/adarrsh/siemens-ix-mcp/skills"
export IX_DROP_DB="/Users/adarrsh/siemens-ix-mcp/data/drops.sqlite"
export IX_RERANK_THRESHOLD="0.75"
export IX_MAX_KEPT_CHUNKS="6"
export IX_MAX_CONTEXT_CHARS="4500"
export IX_DEFAULT_VERSION="latest"

exec /Users/adarrsh/siemens-ix-mcp/.venv/bin/python -m siemens_ix_mcp
