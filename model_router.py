"""Single source of truth for model role → endpoint mapping.

All files must import from here instead of hardcoding URLs or ports.
When changing model routing, update ONLY this file.
"""
import os

ROLES = {
    "planner":  {
        "model": os.environ.get("PLANNER_MODEL", "mlx-community/Ling-mini-2.0-4bit"),
        "url":   os.environ.get("PLANNER_URL", "http://localhost:8801/v1"),
        "role_description": "Decomposes goals into task graphs. Orchestration only.",
    },
    "reviewer": {
        "model": os.environ.get("REVIEWER_MODEL", "mlx-community/Ling-mini-2.0-4bit"),
        "url":   os.environ.get("REVIEWER_URL", "http://localhost:8801/v1"),
        "role_description": "Reviews generated code for correctness. Does not write code.",
    },
    "coder":    {
        "model": os.environ.get("CODER_MODEL", "AtomicChat/Ornith-9B-MLX-6bit"),
        "url":   os.environ.get("CODER_URL", "http://localhost:8800/v1"),
        "role_description": "Generates code from task specifications.",
    },
    "fallback": {
        "model": os.environ.get("FALLBACK_MODEL", "AtomicChat/Ornith-9B-MLX-6bit"),
        "url":   os.environ.get("FALLBACK_URL", "http://localhost:8800/v1"),
        "role_description": "Fallback coder when primary is unavailable.",
    },
}

def get_model(role: str) -> str:
    return ROLES[role]["model"]

def get_url(role: str) -> str:
    return ROLES[role]["url"]

def get_endpoint(role: str) -> str:
    return f"{get_url(role)}/chat/completions"
