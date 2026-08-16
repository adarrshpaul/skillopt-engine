"""Protocol interfaces for all SkillOpt subsystems.

Depend on these contracts, not on concrete implementations.
This enables:
- Mocking in unit tests
- Swapping implementations (e.g., SQLite → Postgres)
- Feature modularity
- Capability Seams (Service Definition / Provider / Consumer)
"""
from typing import Protocol, Dict, Any, List, Optional, runtime_checkable
from dataclasses import dataclass, field
import time

# ── Core Subsystem Protocols ──

@runtime_checkable
class LLMClient(Protocol):
    def generate(self, system_prompt: str, user_prompt: str, **kwargs) -> str: ...

@runtime_checkable
class GraphStore(Protocol):
    def add_node(self, node_id: str, node_type: str, content: str, **kwargs) -> None: ...
    def add_edge(self, src: str, dst: str, label: str) -> None: ...
    def get_graph(self) -> Dict[str, Any]: ...

@runtime_checkable
class AdmissionController(Protocol):
    def admit(self, request_id: str, priority: int, payload: str) -> Dict[str, Any]: ...

@runtime_checkable
class CheckpointStore(Protocol):
    def save(self, token: str, state: Dict[str, Any]) -> None: ...
    def load(self, token: str) -> Optional[Dict[str, Any]]: ...

@runtime_checkable
class VectorIndex(Protocol):
    def add_documents(self, docs: List[Dict[str, Any]]) -> None: ...
    def query(self, text: str, top_k: int = 5) -> List[Dict[str, Any]]: ...


# ── Supporting Types for Capability Seams ──

@dataclass
class CommandResult:
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: float = 0.0

@dataclass
class GuardDecision:
    decision: str  # "allow", "deny", "ask", "warn"
    rule_id: str = ""
    reason: str = ""

@dataclass
class GuardContext:
    worktree_root: str = ""
    active_role: str = ""
    turn_index: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class SessionEventData:
    event_type: str
    seq: int = 0
    timestamp: float = field(default_factory=time.time)
    session_id: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)
    tokens_in: int = 0
    tokens_out: int = 0

@dataclass
class GateResult:
    passed: bool
    score: float = 0.0
    feedback: str = ""
    details: Dict[str, Any] = field(default_factory=dict)

@dataclass
class TaskSpecData:
    task_id: str
    description: str
    target_files: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    test_cmd: str = ""
    status: str = "pending"
    assigned_to: str = ""

@dataclass
class DriftReport:
    task_id: str
    drift_type: str
    detail: str


# ── Capability Seam Protocols ──

@runtime_checkable
class SandboxExecutor(Protocol):
    """Service Definition: Execution environment abstraction.
    Providers: NativeVenvSandbox, E2BSandbox, DockerSandbox, TmuxSandbox"""
    def execute_command(self, cmd: str, timeout: int = 120) -> CommandResult: ...
    def write_file(self, path: str, content: str) -> None: ...
    def read_file(self, path: str) -> str: ...
    def teardown(self) -> None: ...

@runtime_checkable
class ToolGuard(Protocol):
    """Service Definition: Pre-execution safety gate (monotonic, non-reorderable).
    Providers: CommandSafetyGuard, ScopeLeashGuard, TimeoutGuard"""
    def evaluate(self, tool_name: str, args: Dict[str, Any], context: GuardContext) -> GuardDecision: ...

@runtime_checkable
class SessionLedger(Protocol):
    """Service Definition: Append-only execution event log.
    Providers: JSONLSessionLedger, SQLiteSessionLedger"""
    def append(self, event: Any) -> int: ...
    def replay(self, from_seq: int = 0) -> List[Any]: ...
    def fork(self, boundary_seq: int) -> 'SessionLedger': ...

@runtime_checkable
class ReviewGate(Protocol):
    """Service Definition: Independent code quality verification.
    Providers: ASTReviewGate, LLMSemanticReviewGate, SkillOptGate"""
    def evaluate(self, code: str, description: str, target_file: str) -> GateResult: ...

@runtime_checkable
class TaskLedger(Protocol):
    """Service Definition: Structured plan/task tracking.
    Providers: MarkdownTaskLedger, SQLiteTaskLedger"""
    def add_task(self, task: TaskSpecData) -> str: ...
    def update_status(self, task_id: str, status: str) -> None: ...
    def get_drift(self) -> List[DriftReport]: ...
