# Workspace Context

> **All AI agents read this file before starting any task in this workspace.**

## Who You Are Working With

You are one of potentially multiple AI agents working in this shared workspace.
Other agents (Cursor Composer, GitHub Copilot, Antigravity/Gemini) may be working
concurrently. Coordinate via `.tasks/` — never duplicate work another agent claimed.

## Projects

### 1. Machine — IMS / OKF Learning
- **Path**: `/Users/adarrsh/machine`
- **Stack**: Python (scraping, parsing), Angular (preview UI)
- **Purpose**: Crawl IMS content, build OKF (Opinionated Knowledge File), generate flashcards
- **Key files**: `crawl.py`, `build_okf.py`, `ims_parsers.py`, `requirements.txt`

### 2. Siemens iX MCP Server
- **Path**: `/Users/adarrsh/siemens-ix-mcp`
- **Stack**: Python (FastMCP / mcp SDK), SQLite knowledge base
- **Purpose**: MCP server that helps agents build correct Siemens iX UI on the first try
- **Key files**: `src/siemens_ix_mcp/server.py`, `knowledge/`, `skills/`, `data/drops.sqlite`

## Shared MCP Tools (available to all agents)

Connect to `siemens-ix-mcp` for:
- `ix_list_versions` — available iX versions
- `ix_list_components` — all iX components for a version
- `ix_retrieve` — semantic search over the OKF knowledge base
- `ix_build_ui` — generate verified Siemens iX UI code
- `ix_check_standards` — validate code against iX coding standards

## Coding Standards

- Python: follow existing style in each project, use type hints
- Angular/TypeScript: Siemens iX components only (no raw HTML elements for UI)
- Always read `AGENTS.md` in the project root before modifying code
- Write tests for non-trivial logic

## Task Coordination

1. Check `/Users/adarrsh/workspace/.tasks/queue.md` for pending tasks
2. Check `/Users/adarrsh/workspace/.tasks/in-progress.md` to avoid duplicating work
3. Write results to `/Users/adarrsh/workspace/.tasks/done/`
