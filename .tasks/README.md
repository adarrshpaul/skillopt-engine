# Agent Task System — README

This `.tasks/` directory is the **shared coordination layer** for all IDE agents.

## Files

| File | Purpose |
|------|---------|
| `queue.md` | Pending tasks — any agent can pick these up |
| `in-progress.md` | Tasks currently being worked on (claimed) |
| `done/TASK-NNN.md` | Completed task results |
| `notes/` | Free-form cross-agent notes and observations |

## Agent Protocol

### Picking up a task
1. Read `queue.md`
2. Choose a task
3. Move it to `in-progress.md`, add your agent name and timestamp
4. Do the work
5. Write results to `done/TASK-NNN.md`
6. Remove from `in-progress.md`

### Handing off to another agent
Write a note in `notes/handoff-TASK-NNN.md` with:
- What you did
- What's left
- Which agent should pick it up next
- Any relevant file paths

### Leaving context for other agents
Drop a `notes/context-YYYYMMDD.md` with any observations, decisions,
or information that would help other agents working in this workspace.

## Connected Projects

| Project | Path | Primary Agent |
|---------|------|--------------|
| Machine (IMS/OKF) | `/Users/adarrsh/machine` | Any |
| Siemens iX MCP | `/Users/adarrsh/siemens-ix-mcp` | Any |

## Shared MCP Server

All agents connect to the same `siemens-ix-mcp` tool server.
See `/Users/adarrsh/workspace/mcp-server.log` for server status when running.
