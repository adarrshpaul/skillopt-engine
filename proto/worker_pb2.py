"""Worker protobuf message stubs for checkpoint and resume contracts."""
from dataclasses import dataclass

@dataclass
class PreemptRequest:
    task_id: str = ""
    progress: str = ""

@dataclass
class PreemptResponse:
    checkpoint_token: str = ""

@dataclass
class ResumeRequest:
    checkpoint_token: str = ""

@dataclass
class ResumeResponse:
    status: str = "RESUMED"
