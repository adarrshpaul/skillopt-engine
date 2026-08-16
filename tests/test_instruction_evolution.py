import pytest
import os
import tempfile
from pathlib import Path
from core.instruction_evolution import RuleEvolutionEngine
from core.session_ledger import JSONLSessionLedger, SessionEvent

@pytest.fixture
def temp_workspace():
    with tempfile.TemporaryDirectory() as d:
        yield d

def test_analyze_session_extracts_failures(temp_workspace):
    engine = RuleEvolutionEngine(temp_workspace)
    
    # Create a mock ledger
    ledger_path = Path(temp_workspace) / "mock_session.jsonl"
    ledger = JSONLSessionLedger(ledger_path)
    
    # Add events
    ledger.append(SessionEvent(event_type="assistant/message", payload={"content": "<execute>write_file(\"bad.py\", \"code\")</execute>"}))
    ledger.append(SessionEvent(event_type="review/result", payload={"status": "REQUEST_CHANGES", "severity": "MAJOR", "critique": "Missing docstring in module."}))
    
    failures = engine.analyze_session(ledger)
    assert len(failures) == 1
    assert "Missing docstring" in failures[0]["critique"]
    assert "write_file" in failures[0]["coder_action"]

def test_apply_rule_appends_to_strict_rules(temp_workspace):
    engine = RuleEvolutionEngine(temp_workspace)
    rules_path = Path(temp_workspace) / "STRICT_RULES.md"
    
    # Test file doesn't exist yet
    engine.apply_rule("All files must have a docstring.")
    assert rules_path.exists()
    content = rules_path.read_text()
    assert "All files must have a docstring." in content
    assert "- All files must have a docstring." in content
    
    # Test formatting codeblocks
    engine.apply_rule("```\n- Never use eval.\n```")
    content = rules_path.read_text()
    assert "Never use eval" in content
    assert "```" not in content

def test_build_synthesis_prompt(temp_workspace):
    engine = RuleEvolutionEngine(temp_workspace)
    failure = {
        "critique": "Variable names are too short",
        "coder_action": "x = 1"
    }
    prompt = engine.build_synthesis_prompt(failure)
    assert "Variable names are too short" in prompt
    assert "x = 1" in prompt
    assert "synthesize a single, deterministic, mechanical rule" in prompt
