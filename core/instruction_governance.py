"""
Reporails Instruction Governance Engine.
Inspired by Reporails CLI (https://github.com/reporails/cli) and STRICT_RULES.md.
Performs mechanical and deterministic rule enforcement on system instructions and user goals
prior to model dispatch, preventing catastrophic forgetting and vague, non-testable goals.
"""
import re
import os
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple
from pathlib import Path

@dataclass
class LocalFinding:
    severity: str  # "error", "warning", "info"
    rule_id: str
    message: str


class ReporailsLinter:
    """
    Native implementation of the Reporails Instruction Governance Engine.
    Enforces deterministic constraints on system instructions and goals.
    """
    
    # "Vibes-based" words that cause poor LLM adherence
    VIBE_WORDS = [
        r'\b(robust)\b',
        r'\b(good)\b',
        r'\b(clean)\b',
        r'\b(efficient)\b',
        r'\b(be careful)\b',
        r'\b(make sure it works)\b',
        r'\b(high quality)\b',
        r'\b(fast)\b',
        r'\b(nice)\b'
    ]

    # Dangerous command patterns in goals
    DANGEROUS_PATTERNS = [
        (r'\brm\s+-rf\s+[/~]', "destructive_rm", "Destructive recursive deletion of root or home directory"),
        (r'\bcurl\s+.*\|\s*bash\b', "pipe_to_shell", "Remote script piped directly to shell"),
        (r'\bchmod\s+777\b', "insecure_permissions", "Insecure wide-open permissions (777)")
    ]
    
    def __init__(self):
        self.findings: List[LocalFinding] = []
        
    def lint_workspace(self, workspace_root: str, system_prompt: str) -> List[LocalFinding]:
        self.findings.clear()
        
        # 1. Mechanical Checks on System Prompt
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
        return list(self.findings)

    def lint_goal(self, goal: str) -> List[LocalFinding]:
        """Lints user-submitted goals against mechanical rules and vague constraints."""
        goal_findings: List[LocalFinding] = []
        goal_lower = goal.lower()

        # 1. Check for dangerous destructive patterns
        for pattern, rule_id, desc in self.DANGEROUS_PATTERNS:
            if re.search(pattern, goal):
                goal_findings.append(LocalFinding(
                    "error",
                    f"security/{rule_id}",
                    f"Forbidden destructive command pattern detected: {desc}."
                ))

        # 2. Vibe Check in user goal (Warnings for prompt improvement)
        for pattern in self.VIBE_WORDS:
            m = re.search(pattern, goal_lower)
            if m:
                matched = m.group(1)
                goal_findings.append(LocalFinding(
                    "warning",
                    "deterministic/vibe_check",
                    f"Subjective goal term detected: '{matched}'. Ensure specific test criteria are defined."
                ))

        # 3. Specificity Check: does it mention a target file or module?
        has_file_target = bool(re.search(r'\b[a-zA-Z0-9_\-]+\.(?:py|js|ts|json|sh|html|css|md|yaml|yml)\b', goal))
        if not has_file_target:
            goal_findings.append(LocalFinding(
                "info",
                "mechanical/file_targeting",
                "No explicit target filename (e.g. 'app.py') detected in goal. Orchestrator will infer target files."
            ))

        return goal_findings

    def lint_all(self, workspace_root: str, system_prompt: str, goal: str = "") -> Tuple[List[LocalFinding], bool]:
        """
        Runs comprehensive instruction governance across workspace, system prompt, and goal.
        Returns (findings, has_fatal_errors).
        """
        findings = self.lint_workspace(workspace_root, system_prompt)
        if goal:
            findings.extend(self.lint_goal(goal))

        severity_order = {"error": 0, "warning": 1, "info": 2}
        findings.sort(key=lambda x: severity_order.get(x.severity, 9))
        has_fatal = any(f.severity == "error" for f in findings)
        return findings, has_fatal
        
    def _mechanical_checks(self, content: str):
        # 1A. Token/Length Limits (Roughly 4 chars per token)
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
                    "warning" if source == "STRICT_RULES.md" else "error",
                    "deterministic/vibe_check",
                    f"[{source}] Vague term detected: '{matched}'. Replace with concrete, assertive constraints."
                ))
