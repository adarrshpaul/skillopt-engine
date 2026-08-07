import unittest
import time
import ast
from pathlib import Path
from agentic_ide_engine import AgenticSystemOrchestrator, TaskNode
from chroma_store import ChromaVectorMemory

class TestAgenticIDEHarmessEvolution(unittest.TestCase):
    """
    Exhaustive test suite verifying the evolutionary jump to an autonomous
    IDE-native agentic coding harness.
    """

    @classmethod
    def setUpClass(cls):
        cls.workspace_dir = Path("/Users/adarrsh/workspace")
        cls.orchestrator = AgenticSystemOrchestrator(workspace_dir=str(cls.workspace_dir))
        cls.chroma = ChromaVectorMemory()

    def test_task_graph_decomposition(self):
        """Verifies multi-task goal decomposition into structured dependency DAGs."""
        complex_goal = "Build a distributed microservice event processing system with state machine and API gateway"
        tasks = self.orchestrator.decompose_system_goal(complex_goal)
        self.assertGreaterEqual(len(tasks), 3)
        self.assertEqual(tasks[0].target_file, "models.py")
        self.assertEqual(tasks[1].target_file, "engine.py")

    def test_chroma_semantic_memory_retrieval(self):
        """Verifies ChromaDB semantic search retrieves relevant codebase context."""
        hits = self.chroma.semantic_search("Evaluator-Optimizer loop AST validation", n_results=2)
        self.assertIsInstance(hits, list)
        self.assertGreater(len(hits), 0)
        self.assertIn("document", hits[0])

    def test_evaluator_optimizer_ast_quality_gate(self):
        """Verifies that invalid code is caught by the AST compiler and valid code passes."""
        valid_node = TaskNode("test_valid", "Valid Node", "Valid code", "temp_valid.py")
        res_valid = self.orchestrator.synthesize_code_with_ast_gating(valid_node, "")
        self.assertEqual(res_valid["status"], "PASSED")
        
        # Verify file was written to disk
        written_file = self.workspace_dir / "temp_valid.py"
        self.assertTrue(written_file.exists())
        written_file.unlink() # Cleanup

    def test_end_to_end_system_synthesis_and_execution(self):
        """Verifies the autonomous generation and passing of a full multi-file software system."""
        goal = "Build a distributed microservice event processing system with state machine and API gateway"
        summary = self.orchestrator.execute_autonomous_build(goal)
        self.assertEqual(summary["test_suite_status"], "PASSED")
        self.assertGreaterEqual(summary["tasks_count"], 4)
        self.assertLess(summary["duration_sec"], 5.0)

if __name__ == "__main__":
    unittest.main()
