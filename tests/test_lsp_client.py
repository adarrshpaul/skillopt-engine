import unittest
import tempfile
from pathlib import Path
from core.lsp_client import (
    handle_find_definition,
    handle_find_references,
    handle_document_symbols,
    handle_hover,
    get_symbol_index
)

class TestLSPClient(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.ws = Path(self.tmp_dir.name)

        # Create dummy python files
        self.file_a = self.ws / "service.py"
        self.file_a.write_text(
            'class PaymentService:\n'
            '    """Handles user billing and charges."""\n'
            '    def charge(self, amount: float):\n'
            '        return f"Charged {amount}"\n'
        )

        self.file_b = self.ws / "main.py"
        self.file_b.write_text(
            'from service import PaymentService\n\n'
            'def main():\n'
            '    svc = PaymentService()\n'
            '    svc.charge(99.0)\n'
        )

        # Force re-index on tmp workspace
        idx = get_symbol_index(str(self.ws))
        idx.workspace_root = str(self.ws)
        idx.cache_file = str(self.ws / ".repomap_cache.json")
        idx.scan_workspace()

        self.context = {"workspace_root": str(self.ws)}

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_handle_find_definition(self):
        out = handle_find_definition({"symbol": "PaymentService"}, self.context)
        self.assertIn("Found 1 definition(s)", out)
        self.assertIn("service.py", out)
        self.assertIn("Handles user billing", out)

    def test_handle_find_references(self):
        out = handle_find_references({"symbol": "PaymentService"}, self.context)
        self.assertIn("Found", out)
        self.assertIn("main.py", out)

    def test_handle_document_symbols(self):
        out = handle_document_symbols({"path": "service.py"}, self.context)
        self.assertIn("PaymentService", out)
        self.assertIn("charge", out)

    def test_handle_hover(self):
        out = handle_hover({"symbol": "PaymentService"}, self.context)
        self.assertIn("PaymentService (class)", out)
        self.assertIn("Handles user billing", out)

    def test_missing_args(self):
        err = handle_find_definition({}, self.context)
        self.assertIn("ERROR: find_definition requires 'symbol'", err)

        err_doc = handle_document_symbols({}, self.context)
        self.assertIn("ERROR: document_symbols requires 'path'", err_doc)

if __name__ == "__main__":
    unittest.main()
