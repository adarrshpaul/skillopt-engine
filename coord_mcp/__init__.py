"""
Workspace Coordination MCP Server
==================================
A lightweight MCP server for shared task queue management and cross-agent notes.
Supports both FastMCP (Python >= 3.10) and built-in minimal JSON-RPC stdio fallback (Python 3.9+).
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

# ── Paths ──────────────────────────────────────────────────────────────────────
WORKSPACE    = Path.home() / "workspace"
TASKS_DIR    = WORKSPACE / ".tasks"
QUEUE_FILE   = TASKS_DIR / "queue.md"
WIP_FILE     = TASKS_DIR / "in-progress.md"
DONE_DIR     = TASKS_DIR / "done"
NOTES_DIR    = TASKS_DIR / "notes"
CONTEXT_FILE = WORKSPACE / "CONTEXT.md"

for d in (TASKS_DIR, DONE_DIR, NOTES_DIR):
    d.mkdir(parents=True, exist_ok=True)

# ── Core Functions ─────────────────────────────────────────────────────────────

def read_task_queue() -> str:
    """Read the shared task queue."""
    if not QUEUE_FILE.exists():
        return "Queue is empty — no tasks yet."
    return QUEUE_FILE.read_text()


def read_in_progress() -> str:
    """Read which tasks are currently being worked on by other agents."""
    if not WIP_FILE.exists():
        return "Nothing in progress."
    return WIP_FILE.read_text()


def read_context() -> str:
    """Read the shared workspace context (projects, standards, goals)."""
    if not CONTEXT_FILE.exists():
        return "No CONTEXT.md found."
    return CONTEXT_FILE.read_text()


def claim_task(task_id: str, agent_name: str, status: str = "Starting...") -> str:
    """Claim a task from the queue so other agents know it's taken."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    entry = (
        f"\n### {task_id} — claimed by {agent_name}\n"
        f"- **Claimed at**: {timestamp}\n"
        f"- **Status**: {status}\n"
    )
    with WIP_FILE.open("a") as f:
        f.write(entry)
    return f"✔ {task_id} claimed by {agent_name} at {timestamp}"


def complete_task(task_id: str, agent_name: str, result: str) -> str:
    """Mark a task as complete and write the result to the done/ folder."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    done_file = DONE_DIR / f"{task_id}.md"
    done_file.write_text(
        f"# {task_id} — Completed\n\n"
        f"- **Completed by**: {agent_name}\n"
        f"- **Completed at**: {timestamp}\n\n"
        f"## Result\n\n{result}\n"
    )
    if WIP_FILE.exists():
        lines = WIP_FILE.read_text().splitlines(keepends=True)
        in_block = False
        new_lines = []
        for line in lines:
            if line.strip().startswith(f"### {task_id}"):
                in_block = True
            elif in_block and line.strip().startswith("###"):
                in_block = False
            if not in_block:
                new_lines.append(line)
        WIP_FILE.write_text("".join(new_lines))
    return f"✔ {task_id} marked complete. Result written to .tasks/done/{task_id}.md"


def write_note(note_name: str, content: str, agent_name: str) -> str:
    """Write a cross-agent note (handoff, observation, decision log)."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    note_file = NOTES_DIR / f"{note_name}.md"
    note_file.write_text(
        f"# {note_name}\n\n"
        f"- **Author**: {agent_name}\n"
        f"- **Written at**: {timestamp}\n\n"
        f"{content}\n"
    )
    return f"✔ Note written to .tasks/notes/{note_name}.md"


def read_note(note_name: str) -> str:
    """Read a cross-agent note by name (without .md extension)."""
    note_file = NOTES_DIR / f"{note_name}.md"
    if not note_file.exists():
        available = [f.stem for f in NOTES_DIR.glob("*.md")]
        return f"Note '{note_name}' not found. Available: {available}"
    return note_file.read_text()


def list_notes() -> str:
    """List all cross-agent notes in the notes/ folder."""
    notes = sorted(NOTES_DIR.glob("*.md"))
    if not notes:
        return "No notes yet."
    return "\n".join(f"- {n.stem}" for n in notes)


def list_done_tasks() -> str:
    """List all completed tasks."""
    done = sorted(DONE_DIR.glob("*.md"))
    if not done:
        return "No completed tasks yet."
    return "\n".join(f"- {d.stem}" for d in done)


# ── Dispatcher ─────────────────────────────────────────────────────────────────

TOOL_SCHEMAS = [
    {
        "name": "read_task_queue",
        "description": "Read the shared task queue. Call this first before starting any work.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "read_in_progress",
        "description": "Read which tasks are currently being worked on by other agents.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "read_context",
        "description": "Read the shared workspace context (projects, standards, goals).",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "claim_task",
        "description": "Claim a task from the queue so other agents know it's taken.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "e.g. TASK-001"},
                "agent_name": {"type": "string", "description": "Agent claiming the task"},
                "status": {"type": "string", "description": "Status message"},
            },
            "required": ["task_id", "agent_name"],
        },
    },
    {
        "name": "complete_task",
        "description": "Mark a task as complete and write the result to the done/ folder.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "e.g. TASK-001"},
                "agent_name": {"type": "string", "description": "Agent completing the task"},
                "result": {"type": "string", "description": "Detailed result content"},
            },
            "required": ["task_id", "agent_name", "result"],
        },
    },
    {
        "name": "write_note",
        "description": "Write a cross-agent note (handoff, observation, decision log).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "note_name": {"type": "string", "description": "File name without extension"},
                "content": {"type": "string", "description": "Note content"},
                "agent_name": {"type": "string", "description": "Author name"},
            },
            "required": ["note_name", "content", "agent_name"],
        },
    },
    {
        "name": "read_note",
        "description": "Read a cross-agent note by name.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "note_name": {"type": "string", "description": "File name without extension"}
            },
            "required": ["note_name"],
        },
    },
    {
        "name": "list_notes",
        "description": "List all cross-agent notes.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "list_done_tasks",
        "description": "List all completed tasks.",
        "inputSchema": {"type": "object", "properties": {}},
    },
]


def _dispatch(name: str, args: dict[str, Any]) -> str:
    if name == "read_task_queue":
        return read_task_queue()
    elif name == "read_in_progress":
        return read_in_progress()
    elif name == "read_context":
        return read_context()
    elif name == "claim_task":
        return claim_task(args.get("task_id", ""), args.get("agent_name", ""), args.get("status", "Starting..."))
    elif name == "complete_task":
        return complete_task(args.get("task_id", ""), args.get("agent_name", ""), args.get("result", ""))
    elif name == "write_note":
        return write_note(args.get("note_name", ""), args.get("content", ""), args.get("agent_name", ""))
    elif name == "read_note":
        return read_note(args.get("note_name", ""))
    elif name == "list_notes":
        return list_notes()
    elif name == "list_done_tasks":
        return list_done_tasks()
    return f"Unknown tool: {name}"


# ── Built-in Minimal Stdio Server (Python 3.9+) ─────────────────────────────

def run_minimal_stdio() -> None:
    """Minimal MCP JSON-RPC over stdio."""
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue

        method = req.get("method")
        rid = req.get("id")
        params = req.get("params") or {}

        if method == "initialize":
            result = {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "workspace-coordinator", "version": "1.0.0"},
            }
        elif method == "tools/list":
            result = {"tools": TOOL_SCHEMAS}
        elif method == "tools/call":
            name = params.get("name", "")
            args = params.get("arguments") or {}
            text = _dispatch(name, args)
            result = {"content": [{"type": "text", "text": text}]}
        elif method in ("notifications/initialized", "ping"):
            if rid is None:
                continue
            result = {}
        else:
            result = {"error": f"unsupported method {method}"}

        if rid is not None:
            sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": rid, "result": result}) + "\n")
            sys.stdout.flush()


# ── FastMCP Server (Python >= 3.10) ───────────────────────────────────────────

def run_fastmcp() -> None:
    from mcp.server.fastmcp import FastMCP

    fmcp = FastMCP("workspace-coordinator")
    fmcp.tool()(read_task_queue)
    fmcp.tool()(read_in_progress)
    fmcp.tool()(read_context)
    fmcp.tool()(claim_task)
    fmcp.tool()(complete_task)
    fmcp.tool()(write_note)
    fmcp.tool()(read_note)
    fmcp.tool()(list_notes)
    fmcp.tool()(list_done_tasks)
    fmcp.run(transport="stdio")


# ── Entry point ────────────────────────────────────────────────────────────────

def main() -> None:
    try:
        import mcp  # noqa: F401
        run_fastmcp()
    except ImportError:
        run_minimal_stdio()


if __name__ == "__main__":
    main()
