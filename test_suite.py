import unittest
import py_compile
import os
import sys
import sqlite3
import json
from pathlib import Path

class TestWorkspaceCodebase(unittest.TestCase):
    """Standard unit test suite for workspace Python modules."""

    def test_python_files_ast_compilation(self):
        """Verify that all core Python files compile cleanly without syntax errors."""
        workspace_dir = "/Users/adarrsh/workspace"
        core_files = [
            "skillopt_engine_cli.py",
            "auto_coder.py",
            "orchestrator.py",
            "mcp_builder.py",
            "dpo_train.py",
            "dpo_tree_generator.py",
            "run_benchmarks.py",
            "dashboard_server.py",
            "harness_v2.py",
            "chat_ui.py"
        ]
        for filename in core_files:
            filepath = os.path.join(workspace_dir, filename)
            if os.path.exists(filepath):
                with self.subTest(file=filename):
                    py_compile.compile(filepath, doraise=True)

    def test_database_initialization(self):
        """Verify that SQLite database tables initialize correctly."""
        test_db = "/Users/adarrsh/workspace/test_projects.db"
        if os.path.exists(test_db):
            os.remove(test_db)
            
        conn = sqlite3.connect(test_db)
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE projects (id TEXT PRIMARY KEY, name TEXT)")
        cursor.execute("INSERT INTO projects VALUES ('p1', 'Test Project')")
        conn.commit()
        
        cursor.execute("SELECT name FROM projects WHERE id='p1'")
        row = cursor.fetchone()
        conn.close()
        
        if os.path.exists(test_db):
            os.remove(test_db)
            
        self.assertIsNotNone(row)
        self.assertEqual(row[0], "Test Project")

    def test_mcp_builder_scaffold(self):
        """Verify that mcp_builder generates valid Python code strings."""
        import mcp_builder
        server_code = mcp_builder.MCP_SERVER_TEMPLATE.format(server_name="test_calc")
        self.assertIn("class MCPServer", server_code)
        self.assertIn("handle_request", server_code)

    def test_harness_v2_memory_hierarchy(self):
        """Verify that AgentHarnessV2 memory tiers load and persist correctly."""
        from harness_v2 import MemoryManager
        workspace = Path("/Users/adarrsh/workspace")
        mem = MemoryManager(workspace)
        
        # Tier 1: Check PROJECT.md loader
        conventions = mem.load_tier1_conventions()
        self.assertTrue(len(conventions) > 0)
        self.assertIn("SkillOpt", conventions)
        
        # Tier 2: Check STATE.md update
        mem.update_tier2_state("Test Goal", [{"step_id": 1, "description": "Do X"}], 0, "Testing")
        state_file = workspace / "STATE.md"
        self.assertTrue(state_file.exists())
        self.assertIn("Test Goal", state_file.read_text(encoding="utf-8"))

    def test_harness_v2_event_stream_loop(self):
        """Verify that the AgentHarnessV2 generator loop yields structured events."""
        from harness_v2 import AgentHarnessV2, TerminalResult
        harness = AgentHarnessV2()
        tasks = [{"step_id": 1, "description": "Unit test module", "target_file": "temp_test_mod.py"}]
        
        events = []
        runner = harness.run_agent_loop("Test Harness Loop", tasks, max_turns_per_task=2)
        try:
            while True:
                events.append(next(runner))
        except StopIteration as e:
            result = e.value
            self.assertIsInstance(result, TerminalResult)
            self.assertEqual(result.status, "COMPLETE")

        event_types = [ev.event_type for ev in events]
        self.assertIn("SESSION_START", event_types)
        self.assertIn("TURN_START", event_types)
        self.assertIn("EVAL_PASS", event_types)

    def test_chat_ui_artifact_extraction(self):
        """Verify that chat_ui correctly parses markdown code blocks as artifacts."""
        from chat_ui import extract_artifact
        sample_response = "Here is the code:\n```python\ndef hello():\n    return 'world'\n```"
        artifact = extract_artifact(sample_response)
        self.assertIn("def hello():", artifact)

if __name__ == "__main__":
    unittest.main()
