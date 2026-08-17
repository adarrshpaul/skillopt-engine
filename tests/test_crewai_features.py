"""
Unit tests for CrewAI-inspired features:
1. YAML-driven agent configuration registry
2. CognitiveMemory persistence and retrieval
3. Multi-grammar tool parsing for ask_human and delegate_task
4. Orchestrator tool handlers
"""
import os
import unittest
from core.agent_config import AgentConfigRegistry
from core.compaction import CognitiveMemory
from core.tool_pipeline import parse_tool_calls_from_text
from orchestrator import _handle_ask_human, _handle_delegate_task

class TestCrewAIFeatures(unittest.TestCase):

    def test_agent_config_yaml_loading(self):
        registry = AgentConfigRegistry("config/agents.yaml")
        self.assertIn("planner", registry.agents)
        self.assertIn("coder", registry.agents)
        self.assertIn("researcher", registry.agents)
        self.assertIn("debugger", registry.agents)
        
        researcher = registry.get("researcher")
        self.assertEqual(researcher.role, "Technical Researcher & Codebase Investigator")
        self.assertTrue(len(researcher.get_full_prompt()) > 20)

    def test_cognitive_memory(self):
        mem_file = ".test_cognitive_memory.json"
        if os.path.exists(mem_file):
            os.remove(mem_file)
            
        mem = CognitiveMemory(memory_file=mem_file)
        mem.record("discovery", "SQLite connection string requires check_same_thread=False for multithreading", source_task="T01")
        mem.record("error_fix", "Use math.isclose instead of == for float comparisons in physics tests", source_task="T02")
        
        results = mem.query("How to handle sqlite multithreading?")
        self.assertTrue(len(results) > 0)
        self.assertIn("SQLite", results[0].insight)
        
        injection = mem.format_prompt_injection("sqlite multithreading error")
        self.assertIn("COGNITIVE MEMORY", injection)
        
        if os.path.exists(mem_file):
            os.remove(mem_file)

    def test_tool_parsing_ask_human(self):
        raw_text = '<execute>ask_human("Should we support case-insensitive palindromes?")</execute>'
        calls, errors = parse_tool_calls_from_text(raw_text)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0].name, "ask_human")
        self.assertIn("question", calls[0].args)
        self.assertEqual(calls[0].args["question"], "Should we support case-insensitive palindromes?")

    def test_tool_parsing_delegate_task(self):
        raw_text = '<execute>delegate_task(role="researcher", task="Find fastest palindrome algorithm")</execute>'
        calls, errors = parse_tool_calls_from_text(raw_text)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0].name, "delegate_task")
        self.assertEqual(calls[0].args["role"], "researcher")
        self.assertEqual(calls[0].args["task"], "Find fastest palindrome algorithm")

    def test_ask_human_handler_non_interactive(self):
        result = _handle_ask_human({"question": "Clarify requirements"}, {"interactive": False})
        self.assertIn("[Human Response]", result)

if __name__ == "__main__":
    unittest.main()
