import unittest
import tempfile
import os
from pathlib import Path
from core.symbol_index import SymbolIndex, ASTSymbolVisitor

class TestSymbolIndex(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.ws = Path(self.tmp_dir.name)

        # Create dummy python files
        self.file_a = self.ws / "math_mod.py"
        self.file_a.write_text(
            '"""Math utilities module."""\n\n'
            'class Calculator:\n'
            '    """Performs arithmetic."""\n'
            '    def add(self, a, b):\n'
            '        return a + b\n\n'
            'def multiply(x, y):\n'
            '    """Multiplies two numbers."""\n'
            '    return x * y\n'
        )

        self.file_b = self.ws / "app.py"
        self.file_b.write_text(
            'from math_mod import Calculator, multiply\n\n'
            'def run_app():\n'
            '    calc = Calculator()\n'
            '    res = calc.add(2, 3)\n'
            '    return multiply(res, 4)\n'
        )

        self.index = SymbolIndex(workspace_root=str(self.ws), cache_file=".test_cache.json")

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_scan_and_find_definitions(self):
        self.index.scan_workspace()
        defs = self.index.find_definition("Calculator")
        self.assertEqual(len(defs), 1)
        self.assertEqual(defs[0]["kind"], "class")
        self.assertEqual(defs[0]["file_path"], "math_mod.py")
        self.assertEqual(defs[0]["docstring"], "Performs arithmetic.")

        func_defs = self.index.find_definition("multiply")
        self.assertEqual(len(func_defs), 1)
        self.assertEqual(func_defs[0]["kind"], "function")
        self.assertEqual(func_defs[0]["args"], ["x", "y"])

    def test_find_references(self):
        self.index.scan_workspace()
        refs = self.index.find_references("Calculator")
        self.assertGreaterEqual(len(refs), 1)
        self.assertTrue(any(r["file_path"] == "app.py" for r in refs))

    def test_document_symbols(self):
        self.index.scan_workspace()
        syms = self.index.document_symbols("math_mod.py")
        names = [s["name"] for s in syms]
        self.assertIn("Calculator", names)
        self.assertIn("add", names)
        self.assertIn("multiply", names)

    def test_hover(self):
        self.index.scan_workspace()
        info = self.index.hover("multiply")
        self.assertIsNotNone(info)
        self.assertEqual(info["symbol"], "multiply")
        self.assertIn("x, y", info["signature"])
        self.assertEqual(info["docstring"], "Multiplies two numbers.")

    def test_get_condensed_repo_map(self):
        repo_map = self.index.get_condensed_repo_map(max_tokens=500)
        self.assertIn("Workspace Symbol Map", repo_map)
        self.assertIn("math_mod.py", repo_map)
        self.assertIn("Calculator", repo_map)
        self.assertIn("app.py", repo_map)

    def test_incremental_cache(self):
        self.index.scan_workspace()
        cache_path = self.ws / ".test_cache.json"
        self.assertTrue(cache_path.exists())

        # Second scan should hit cache cleanly
        index2 = SymbolIndex(workspace_root=str(self.ws), cache_file=".test_cache.json")
        index2.scan_workspace()
        self.assertEqual(len(index2.definitions), len(self.index.definitions))

if __name__ == "__main__":
    unittest.main()
