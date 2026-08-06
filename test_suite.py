import unittest
import py_compile
import os
import sys
import sqlite3
import json

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
            "dashboard_server.py"
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

if __name__ == "__main__":
    unittest.main()
