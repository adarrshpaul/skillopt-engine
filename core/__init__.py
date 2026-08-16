"""
Core harness package synthesized from DeepSeek Harness & Claude Code Harness architectures.
"""
from core.session_ledger import SessionEvent, JSONLSessionLedger, SQLiteSessionLedger
from core.safety_gate import SafetyGate, evaluate_tool_call, Decision, GuardResult
from core.tool_pipeline import ToolPipeline, ToolCall, ToolResult, parse_tool_calls_from_text
from core.task_ledger import MarkdownTaskLedger, TaskSpec
from core.compaction import CompactionGovernor, save_wip_state, restore_wip_state, clear_wip_state
from core.parallel_executor import WorktreeExecutor, ExecutionResult

__all__ = [
    "SessionEvent",
    "JSONLSessionLedger",
    "SQLiteSessionLedger",
    "SafetyGate",
    "evaluate_tool_call",
    "Decision",
    "GuardResult",
    "ToolPipeline",
    "ToolCall",
    "ToolResult",
    "parse_tool_calls_from_text",
    "MarkdownTaskLedger",
    "TaskSpec",
    "CompactionGovernor",
    "save_wip_state",
    "restore_wip_state",
    "clear_wip_state",
    "WorktreeExecutor",
    "ExecutionResult",
]
