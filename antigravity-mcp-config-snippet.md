# Antigravity MCP Config Snippets

Since `~/.gemini/config/mcp_config.json` is system-protected, add these
manually via **Antigravity Settings → MCP Servers**.

## 1. Workspace Coordinator (always add this)

```json
{
  "workspace-coordinator": {
    "type": "stdio",
    "command": "/Users/adarrsh/siemens-ix-mcp/.venv/bin/python",
    "args": ["-m", "coord_mcp"],
    "env": {
      "PYTHONPATH": "/Users/adarrsh/workspace"
    }
  }
}
```

## 2. Siemens iX MCP (add this for testing your server with Antigravity)

```json
{
  "siemens-ix": {
    "type": "stdio",
    "command": "/Users/adarrsh/siemens-ix-mcp/.venv/bin/python",
    "args": ["-m", "siemens_ix_mcp"],
    "env": {
      "PYTHONPATH": "/Users/adarrsh/siemens-ix-mcp/src:/Users/adarrsh/siemens-ix-mcp",
      "IX_KNOWLEDGE_ROOT": "/Users/adarrsh/siemens-ix-mcp/knowledge",
      "IX_SKILLS_ROOT": "/Users/adarrsh/siemens-ix-mcp/skills",
      "IX_DROP_DB": "/Users/adarrsh/siemens-ix-mcp/data/drops.sqlite",
      "IX_RERANK_THRESHOLD": "0.75",
      "IX_MAX_KEPT_CHUNKS": "6",
      "IX_MAX_CONTEXT_CHARS": "4500",
      "IX_DEFAULT_VERSION": "latest"
    }
  }
}
```
