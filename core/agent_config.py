"""
Agent Configuration loader and registry.
Inspired by CrewAI's agents.yaml pattern with zero external dependencies.
"""
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional, Any, List

@dataclass
class AgentSpec:
    name: str
    role: str
    goal: str
    backstory: str
    model: str = "gemini-flash-latest"
    engine: str = "google"
    temperature: float = 0.1
    system_prompt: str = ""
    tools: List[str] = field(default_factory=list)

    def get_full_prompt(self, base_system_prompt: str = "") -> str:
        if self.system_prompt:
            return self.system_prompt
        prompt = f"You are a {self.role}.\nGoal: {self.goal}\nBackstory: {self.backstory}\n"
        if base_system_prompt:
            prompt += f"\n{base_system_prompt}"
        return prompt


def _simple_yaml_parse(text: str) -> Dict[str, Dict[str, Any]]:
    """Lightweight zero-dependency parser for hierarchical YAML files."""
    agents = {}
    current_agent = None
    current_dict = {}
    in_multiline = False
    multiline_key = None
    multiline_lines = []

    for line in text.splitlines():
        # Multiline string handler (|)
        if in_multiline:
            if line.startswith("    ") or line.strip() == "":
                multiline_lines.append(line[4:] if line.startswith("    ") else "")
                continue
            else:
                current_dict[multiline_key] = "\n".join(multiline_lines)
                in_multiline = False
                multiline_key = None
                multiline_lines = []

        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        # Top-level agent key
        if not line.startswith(" ") and stripped.endswith(":"):
            if current_agent:
                agents[current_agent] = current_dict
            current_agent = stripped[:-1].strip()
            current_dict = {}
            continue

        # Agent properties
        if current_agent and ":" in stripped:
            key, val = stripped.split(":", 1)
            key = key.strip()
            val = val.strip()
            if val == "|":
                in_multiline = True
                multiline_key = key
                multiline_lines = []
            else:
                # Clean up quotes and types
                if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
                    val = val[1:-1]
                elif val.replace(".", "", 1).isdigit():
                    val = float(val) if "." in val else int(val)
                elif val.lower() == "true":
                    val = True
                elif val.lower() == "false":
                    val = False
                current_dict[key] = val

    if in_multiline and multiline_key:
        current_dict[multiline_key] = "\n".join(multiline_lines)
    if current_agent:
        agents[current_agent] = current_dict

    return agents


class AgentConfigRegistry:
    """Registry of loaded agent configurations."""

    def __init__(self, config_path: str = "config/agents.yaml"):
        self.config_path = Path(config_path)
        self.agents: Dict[str, AgentSpec] = {}
        self.load()

    def load(self) -> None:
        """Load agents from YAML or fall back to defaults."""
        data = {}
        if self.config_path.exists():
            try:
                try:
                    import yaml
                    with open(self.config_path, "r", encoding="utf-8") as f:
                        data = yaml.safe_load(f) or {}
                except Exception:
                    with open(self.config_path, "r", encoding="utf-8") as f:
                        data = _simple_yaml_parse(f.read())
            except Exception as e:
                print(f"⚠️ [AgentConfig] Failed to load {self.config_path}: {e}", flush=True)

        for name, spec in data.items():
            self.agents[name] = AgentSpec(
                name=name,
                role=spec.get("role", name.capitalize()),
                goal=spec.get("goal", ""),
                backstory=spec.get("backstory", ""),
                model=spec.get("model", "gemini-flash-latest"),
                engine=spec.get("engine", "google"),
                temperature=float(spec.get("temperature", 0.1)),
                system_prompt=spec.get("system_prompt", ""),
            )

    def get(self, name: str, fallback_role: str = "") -> AgentSpec:
        if name in self.agents:
            return self.agents[name]
        return AgentSpec(
            name=name,
            role=fallback_role or name.capitalize(),
            goal=f"Execute tasks matching the {name} role.",
            backstory=f"Specialist in {name}.",
        )

# Global singleton
agent_registry = AgentConfigRegistry()
