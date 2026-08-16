import re
import os
from dataclasses import dataclass
from typing import List, Dict, Optional
from pathlib import Path

@dataclass
class LocalFinding:
    severity: str
    rule_id: str
    message: str

class ReporailsLinter:
    """
    Native implementation of the Reporails Instruction Governance Engine.
    Performs Mechanical and Deterministic checks on workspace instruction files.
    """
    
    # "Vibes-based" words that cause poor LLM adherence
    VIBE_WORDS = [
        r'\b(robust)\b',
        r'\b(good)\b',
        r'\b(clean)\b',
        r'\b(efficient)\b',
        r'\b(be careful)\b',
        r'\b(make sure it works)\b',
        r'\b(high quality)\b'
    ]
    
    def __init__(self):
        self.findings: List[LocalFinding] = []
        
    def lint_workspace(self, workspace_root: str, system_prompt: str) -> List[LocalFinding]:
        self.findings.clear()
        
        # 1. Mechanical Checks
        self._mechanical_checks(system_prompt)
        
        # 2. Deterministic Checks (on system prompt and STRICT_RULES)
        self._deterministic_checks("CODER_SYSTEM_PROMPT", system_prompt)
        
        rules_path = Path(workspace_root) / "STRICT_RULES.md"
        if rules_path.exists():
            try:
                with open(rules_path, "r", encoding="utf-8") as f:
                    rules_content = f.read()
                self._deterministic_checks("STRICT_RULES.md", rules_content)
            except Exception as e:
                self.findings.append(LocalFinding("warning", "file_read_error", f"Could not read STRICT_RULES.md: {e}"))
                
        # Sort findings (errors first)
        severity_order = {"error": 0, "warning": 1, "info": 2}
        self.findings.sort(key=lambda x: severity_order.get(x.severity, 9))
        return self.findings
        
    def _mechanical_checks(self, content: str):
        # 1A. Token/Length Limits (Roughly 4 chars per token)
        # Reporails limits instruction scope to prevent catastrophic forgetting
        approx_tokens = len(content) // 4
        if approx_tokens > 2000:
            self.findings.append(LocalFinding(
                "error", 
                "mechanical/token_limit", 
                f"System instructions exceed 2000 tokens ({approx_tokens} estimated). This severely degrades LLM adherence. Compress instructions."
            ))
            
    def _deterministic_checks(self, source: str, content: str):
        content_lower = content.lower()
        
        # 2A. Vibe-Check Rejection
        for pattern in self.VIBE_WORDS:
            if re.search(pattern, content_lower):
                matched = re.search(pattern, content_lower).group(1)
                self.findings.append(LocalFinding(
                    "error",
                    "deterministic/vibe_check",
                    f"[{source}] Vague/subjective term detected: '{matched}'. Replace with concrete, assertive constraints (e.g., instead of '{matched} code', use 'must have 90% test coverage')."
                ))
