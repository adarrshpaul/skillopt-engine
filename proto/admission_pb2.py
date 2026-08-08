"""Admission protobuf and dataclass stubs for gRPC and HTTP bridges."""
from dataclasses import dataclass

@dataclass
class AdmitRequest:
    id: str = ""
    priority: int = 1
    payload: str = ""

@dataclass
class AdmitResponse:
    action: str = ""
    reason: str = ""
    checkpoint_token: str = ""
    code: str = ""

@dataclass
class HealthCheckRequest:
    service: str = ""

@dataclass
class HealthCheckResponse:
    status: str = "SERVING"
