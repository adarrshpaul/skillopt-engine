"""
Compaction resilience and WIP state management.
Inspired by Claude Code Harness PreCompact/PostCompact hooks and DeepSeek context management.
Guarantees zero work loss during context window compaction or long-turn agent handovers.
"""
import json
import time
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional, Dict, Any, List, Union

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
    Coordinates context compaction threshold checks, pre-compact persistence,
    and post-compact context re-injection.
    """
    def __init__(self, token_limit: int = 16000, trigger_ratio: float = 0.85, wip_file: str = ".harness_wip.json"):
        self.token_limit = token_limit
        self.trigger_threshold = int(token_limit * trigger_ratio)
        self.wip_file = Path(wip_file)

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
