"""Single source of truth for model role → endpoint mapping.

All files must import from here instead of hardcoding URLs or ports.
When changing model routing, update ONLY this file.
Extended with CCH-style host codec layer and DeepSeek-style adapter registry.
"""
import os
from dataclasses import dataclass, field
from typing import Dict, Optional, Any

@dataclass
class ModelEndpoint:
    model: str
    engine: str = "mlx"  # mlx, ollama, litellm, e2b, remote
    url: str = "http://localhost:8800/v1"
    role_description: str = ""
    api_key: str = ""
    max_tokens: int = 2048
    temperature: float = 0.1
    timeout: int = 120
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def chat_endpoint(self) -> str:
        return f"{self.url.rstrip('/')}/chat/completions"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "model": self.model,
            "engine": self.engine,
            "url": self.url,
            "role_description": self.role_description,
        }

    def __getitem__(self, item: str) -> Any:
        # Dictionary-like backward compatibility
        return getattr(self, item)


# Role registry with environment override support
_REGISTRY: Dict[str, ModelEndpoint] = {
    "planner": ModelEndpoint(
        model=os.environ.get("PLANNER_MODEL", "nvidia/nemotron-3-ultra-550b-a55b:free"),
        engine=os.environ.get("PLANNER_ENGINE", "openrouter"),
        url=os.environ.get("PLANNER_URL", "https://openrouter.ai/api/v1"),
        role_description="Decomposes goals into task graphs. Orchestration only.",
    ),
    "reviewer": ModelEndpoint(
        model=os.environ.get("REVIEWER_MODEL", "nvidia/nemotron-3-super-120b-a12b:free"),
        engine=os.environ.get("REVIEWER_ENGINE", "openrouter"),
        url=os.environ.get("REVIEWER_URL", "https://openrouter.ai/api/v1"),
        role_description="Reviews generated code for correctness. Does not write code.",
    ),
    "coder": ModelEndpoint(
        model=os.environ.get("CODER_MODEL", "poolside/laguna-s-2.1:free"),
        engine=os.environ.get("CODER_ENGINE", "openrouter"),
        url=os.environ.get("CODER_URL", "https://openrouter.ai/api/v1"),
        role_description="Generates code from task specifications.",
    ),
    "fallback": ModelEndpoint(
        model=os.environ.get("FALLBACK_MODEL", "mlx-community/Nanbeige4.1-3B-heretic-4bit"),
        engine=os.environ.get("FALLBACK_ENGINE", "mlx"),
        url=os.environ.get("FALLBACK_URL", "http://localhost:8801/v1"),
        role_description="Local MLX fallback model on Apple Silicon when cloud limits are reached.",
    ),
    "optimizer": ModelEndpoint(
        model=os.environ.get("OPTIMIZER_MODEL", "gpt-4o"),
        engine=os.environ.get("OPTIMIZER_ENGINE", "litellm"),
        url=os.environ.get("OPTIMIZER_URL", "https://api.openai.com/v1"),
        role_description="Optimizer LLM for SkillOpt reflection and aggregation.",
        api_key=os.environ.get("OPENAI_API_KEY", ""),
    ),
}

# Backward compatible ROLES dict view
class _RolesDict(dict):
    def __getitem__(self, key: str):
        if key in _REGISTRY:
            return _REGISTRY[key].to_dict()
        return super().__getitem__(key)

    def get(self, key: str, default=None):
        if key in _REGISTRY:
            return _REGISTRY[key].to_dict()
        return default

ROLES = _RolesDict()


def get(role: str) -> ModelEndpoint:
    """Get full endpoint config for a role."""
    if role not in _REGISTRY:
        raise KeyError(f"Unknown role '{role}'. Available: {list(_REGISTRY.keys())}")
    return _REGISTRY[role]


def register(role: str, endpoint: ModelEndpoint) -> None:
    """Dynamically register or override a role at runtime."""
    _REGISTRY[role] = endpoint


def get_model(role: str) -> str:
    return get(role).model


def get_engine(role: str) -> str:
    return get(role).engine


def get_url(role: str) -> str:
    return get(role).url


def get_endpoint(role: str) -> str:
    return get(role).chat_endpoint
