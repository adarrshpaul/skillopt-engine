import os
import re
from typing import List, Dict, Tuple, Optional
from pathlib import Path
from core.session_ledger import JSONLSessionLedger, SessionEvent

class RuleEvolutionEngine:
    """
    Active Instruction Governance: Automatically evolves STRICT_RULES.md
    based on Reviewer rejections in the ReAct loop.
    """
    def __init__(self, workspace_root: str):
        self.workspace_root = Path(workspace_root)
        self.rules_path = self.workspace_root / "STRICT_RULES.md"
        
    def analyze_session(self, ledger: JSONLSessionLedger) -> List[Dict[str, str]]:
        """
        Scans the session ledger for Reviewer rejections.
        Returns a list of extracted failure contexts to synthesize into rules.
        """
        events = ledger.replay(0)
        failures = []
        
        for i, event in enumerate(events):
            if event.event_type == "review/result":
                payload = event.payload
                
                # Identify if this was a rejection
                status = payload.get("status")
                severity = payload.get("severity")
                if status == "REQUEST_CHANGES" or severity in ["CRITICAL", "MAJOR"]:
                    
                    # Backtrack to find the Coder's last action
                    coder_action = ""
                    for j in range(i-1, max(-1, i-6), -1):
                        prev_event = events[j]
                        if prev_event.event_type == "assistant/message":
                            coder_action = prev_event.payload.get("content", "")
                            break
                        if prev_event.event_type == "tool/call":
                            coder_action = str(prev_event.payload)
                            break
                    
                    critique = payload.get("critique") or payload.get("message", str(payload))
                    failures.append({
                        "critique": critique,
                        "coder_action": coder_action
                    })
                    
        return failures

    def build_synthesis_prompt(self, failure: Dict[str, str]) -> str:
        """
        Creates the prompt to ask the Planner model to synthesize a new governance rule.
        """
        return f"""You are the SkillOpt Instruction Governance Engine.
A Coder agent failed a task and received the following critique from the Reviewer:

<critique>
{failure['critique']}
</critique>

The Coder's last action before the critique was:
<action>
{failure['coder_action']}
</action>

Your task is to synthesize a single, deterministic, mechanical rule to add to STRICT_RULES.md to prevent this mistake in future sessions.
The rule MUST:
1. Be actionable and specific.
2. Avoid subjective "vibe" words (e.g., "robust", "good", "efficient", "careful").
3. Be formatted as a single markdown bullet point starting with "- ".

Output ONLY the new rule string. Do not output any other text, reasoning, or markdown formatting blocks.
"""

    def apply_rule(self, new_rule: str):
        """
        Appends the synthesized rule to STRICT_RULES.md.
        """
        rule_text = new_rule.strip()
        if not rule_text:
            return
        
        # Remove any surrounding markdown code block syntax
        if rule_text.startswith("```") and rule_text.endswith("```"):
            lines = rule_text.split('\n')
            if len(lines) > 2:
                rule_text = '\n'.join(lines[1:-1]).strip()
            
        if not rule_text.startswith("-") and not rule_text[0].isdigit():
            rule_text = "- " + rule_text
            
        # Ensure the file exists
        if not self.rules_path.exists():
            with open(self.rules_path, "w", encoding="utf-8") as f:
                f.write("# Core Rules\n")
                
        with open(self.rules_path, "a", encoding="utf-8") as f:
            f.write(f"\n{rule_text}\n")
