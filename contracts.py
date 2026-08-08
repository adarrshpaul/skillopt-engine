"""Protocol interfaces for all SkillOpt subsystems.

Depend on these contracts, not on concrete implementations.
This enables:
- Mocking in unit tests
- Swapping implementations (e.g., SQLite → Postgres)
- Feature modularity
"""
from typing import Protocol, Dict, Any, List, Optional, runtime_checkable

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
