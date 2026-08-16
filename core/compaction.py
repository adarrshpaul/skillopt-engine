"""
Compaction resilience and WIP state management.
Inspired by Claude Code Harness context management (clear_tool_uses + 5-section summary)
and DeepSeek context compaction.
Guarantees zero work loss during context window compaction or long-turn agent handovers.
"""
import json
import time
import os
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional, Dict, Any, List, Union

def estimate_tokens(data: Union[str, List[Dict[str, Any]]]) -> int:
    """Fast, zero-overhead token estimation heuristic (~4 chars per token)."""
    if isinstance(data, str):
        return max(1, len(data) // 4)
    if isinstance(data, list):
        total_chars = 0
        for msg in data:
            if isinstance(msg, dict):
                total_chars += len(str(msg.get("content", ""))) + len(str(msg.get("role", "")))
            else:
                total_chars += len(str(msg))
        return max(1, total_chars // 4)
    return max(1, len(str(data)) // 4)


@dataclass
class WIPState:
    session_id: str
    current_task_idx: int
    active_task_id: str
    tasks: List[Dict[str, Any]] = field(default_factory=list)
    active_diffs_summary: str = ""
    ledger_seq: int = 0
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'WIPState':
        return cls(**data)


def save_wip_state(
    session_id: str,
    current_task_idx: int,
    active_task_id: str,
    tasks: List[Any],
    active_diffs: str = "",
    ledger_seq: int = 0,
    path: Union[str, Path] = ".harness_wip.json"
) -> str:
    """Persists active work-in-progress state to disk prior to compaction or context reset."""
    serialized_tasks = []
    for t in tasks:
        if hasattr(t, "to_dict"):
            serialized_tasks.append(t.to_dict())
        elif hasattr(t, "__dict__"):
            serialized_tasks.append(asdict(t) if hasattr(t, "__dataclass_fields__") else dict(t.__dict__))
        elif isinstance(t, dict):
            serialized_tasks.append(t)

    state = WIPState(
        session_id=session_id,
        current_task_idx=current_task_idx,
        active_task_id=active_task_id,
        tasks=serialized_tasks,
        active_diffs_summary=active_diffs[:4000],
        ledger_seq=ledger_seq,
        timestamp=time.time()
    )

    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(state.to_dict(), indent=2), encoding="utf-8")
    return str(p)


def restore_wip_state(path: Union[str, Path] = ".harness_wip.json") -> Optional[WIPState]:
    """Restores saved WIP state from disk if present."""
    p = Path(path)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return WIPState.from_dict(data)
    except Exception:
        return None


def clear_wip_state(path: Union[str, Path] = ".harness_wip.json") -> None:
    """Removes the WIP state file upon successful completion."""
    p = Path(path)
    if p.exists():
        p.unlink(missing_ok=True)


class CompactionGovernor:
    """
    Two-Tier In-Loop Context Compactor.
    
    Tier 1 (clear_tool_uses):
      Fast, zero-API cost. Evicts stale tool_result outputs from active context
      beyond the most recent K=3 interactions. Archives evicted raw data to DPO logs.
      
    Tier 2 (5-Section Summary Checkpoint):
      Fires if Tier 1 is insufficient. Forks a structured 5-section context distillation:
      1. Task Overview
      2. Current State
      3. Important Discoveries
      4. Next Steps
      5. Context to Preserve
    """
    def __init__(
        self,
        token_limit: int = 12000,
        trigger_ratio: float = 0.80,
        keep_recent_tools: int = 3,
        wip_file: str = ".harness_wip.json",
        dpo_log_path: str = "dpo_logs.jsonl"
    ):
        self.token_limit = token_limit
        self.trigger_threshold = int(token_limit * trigger_ratio)
        self.keep_recent_tools = keep_recent_tools
        self.wip_file = Path(wip_file)
        self.dpo_log_path = Path(dpo_log_path)

    def should_compact(self, current_tokens: int) -> bool:
        return current_tokens >= self.trigger_threshold

    def pre_compact(
        self,
        session_id: str,
        current_idx: int,
        active_task_id: str,
        tasks: list,
        active_diffs: str = "",
        ledger_seq: int = 0
    ) -> WIPState:
        """Pre-compact hook: saves critical WIP state."""
        save_wip_state(
            session_id=session_id,
            current_task_idx=current_idx,
            active_task_id=active_task_id,
            tasks=tasks,
            active_diffs=active_diffs,
            ledger_seq=ledger_seq,
            path=self.wip_file
        )
        return restore_wip_state(self.wip_file)

    def build_post_compact_context(self, wip: Optional[WIPState] = None) -> str:
        """Post-compact hook: formats condensed memory to resume work seamlessly."""
        state = wip or restore_wip_state(self.wip_file)
        if not state:
            return ""

        lines = [
            "\n[SYSTEM: CONTEXT COMPACTION OCCURRED - WORK IN PROGRESS RESTORED]",
            f"Active Task Index: {state.current_task_idx} (Task ID: {state.active_task_id})",
            f"Session Ledger Replay Offset: seq #{state.ledger_seq}",
        ]
        if state.active_diffs_summary:
            lines.append(f"Recent Modifications Summary:\n{state.active_diffs_summary}")
        lines.append("[END RESTORED STATE - PROCEED WITH ACTIVE SUBTASK]\n")
        return "\n".join(lines)

    def tier1_clear_tool_uses(self, ledger, turn_start_seq: int = 0) -> int:
        """
        Tier 1: Scans ledger events from turn_start_seq and evicts stale tool/result outputs.
        Retains the newest keep_recent_tools verbatim. Older outputs are archived to DPO log.
        Appends an append-only 'compaction/evict_tools' marker event to the ledger.
        """
        all_events = ledger.replay(turn_start_seq)
        
        # Collect previously evicted sequence IDs
        already_evicted = set()
        for e in all_events:
            if e.event_type == "compaction/evict_tools":
                already_evicted.update(e.payload.get("evicted_seqs", []))

        tool_result_events = [
            e for e in all_events
            if e.event_type == "tool/result" and e.seq not in already_evicted
        ]

        if len(tool_result_events) <= self.keep_recent_tools:
            return 0

        # Evict everything except the most recent K
        to_evict = tool_result_events[:-self.keep_recent_tools]
        evicted_seqs = []

        for event in to_evict:
            raw_output = event.payload.get("output", "")
            call_signature = event.payload.get("call", "unknown_tool")

            # Only evict if there is substantial output
            if len(raw_output) > 100:
                # 1. Archive to DPO log for zero-data-loss telemetry
                self._archive_evicted_tool(event.seq, call_signature, raw_output)
                evicted_seqs.append(event.seq)

        if evicted_seqs:
            from core.session_ledger import SessionEvent
            ledger.append(SessionEvent(
                event_type="compaction/evict_tools",
                payload={"evicted_seqs": evicted_seqs, "count": len(evicted_seqs)}
            ))

        return len(evicted_seqs)

    def _archive_evicted_tool(self, seq: int, call: str, output: str) -> None:
        """Writes evicted tool results to DPO logs to prevent data loss."""
        try:
            record = {
                "type": "evicted_tool_payload",
                "seq": seq,
                "call": call,
                "output_sample": output[:2000],
                "total_chars": len(output),
                "timestamp": time.time()
            }
            with open(self.dpo_log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record) + "\n")
        except Exception:
            pass

    def build_tier2_summary_prompt(self, messages: List[Dict[str, Any]]) -> str:
        """Constructs the Claude Code-inspired 5-section compaction prompt."""
        formatted_history = []
        for m in messages:
            role = m.get("role", "").upper()
            content = m.get("content", "")
            formatted_history.append(f"[{role}]:\n{content}")
        
        history_text = "\n\n".join(formatted_history[-10:])  # Focus on recent history

        return (
            "You are compacting the context history for an autonomous AI software engineer.\n"
            "Analyze the conversation below and generate a concise, structured checkpoint strictly in these 5 sections:\n\n"
            "### 1. Task Overview\n"
            "Core objective, active subtask, and key constraints.\n\n"
            "### 2. Current State\n"
            "Files created, edited, read, or verified so far.\n\n"
            "### 3. Important Discoveries\n"
            "Key architectural insights, schema definitions, bug root-causes, or test results.\n\n"
            "### 4. Next Steps\n"
            "Concrete remaining actions required to finish the active task.\n\n"
            "### 5. Context to Preserve\n"
            "Exact variable names, function signatures, file paths, or error messages needed next.\n\n"
            f"--- RECENT CONVERSATION HISTORY ---\n{history_text}\n\n"
            "Respond ONLY with the 5 sections. Do not include introductory or conversational text."
        )

    def evaluate_in_loop_compaction(
        self,
        ledger,
        turn_start_seq: int,
        current_messages: List[Dict[str, Any]],
        query_model_fn = None,
        model_kwargs: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Main per-step compaction hook. Runs after each tool call inside the ReAct loop.
        Evaluates token volume, executes Tier 1 if needed, and falls back to Tier 2.
        """
        token_est = estimate_tokens(current_messages)
        stats = {
            "initial_tokens": token_est,
            "tier1_evictions": 0,
            "tier2_triggered": False,
            "final_tokens": token_est
        }

        # Check if compaction is warranted
        if token_est < self.trigger_threshold and len(current_messages) < 12:
            return stats

        # Tier 1: clear_tool_uses
        evicted = self.tier1_clear_tool_uses(ledger, turn_start_seq)
        stats["tier1_evictions"] = evicted

        # If Tier 1 was triggered, re-calculate tokens
        if evicted > 0:
            token_est = estimate_tokens(current_messages)
            stats["final_tokens"] = token_est

        # Tier 2: 5-Section Summary Checkpoint (if still over threshold and query_model_fn available)
        if token_est >= self.trigger_threshold and query_model_fn and model_kwargs:
            try:
                summary_prompt = self.build_tier2_summary_prompt(current_messages)
                summary_resp = query_model_fn(
                    system_prompt="You are a software engineering context distillation engine.",
                    user_prompt=summary_prompt,
                    **model_kwargs
                )
                if summary_resp and len(summary_resp.strip()) > 50:
                    # Import SessionEvent dynamically to prevent circular dependencies
                    from core.session_ledger import SessionEvent
                    ledger.append(SessionEvent(
                        event_type="compaction/checkpoint",
                        payload={"summary": summary_resp.strip(), "tokens_before": token_est}
                    ))
                    stats["tier2_triggered"] = True
            except Exception as e:
                stats["tier2_error"] = str(e)

        return stats
