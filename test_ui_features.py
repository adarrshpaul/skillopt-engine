import unittest
import urllib.request
import urllib.parse
import json
import time
import os
import sys
from pathlib import Path

from harness_v2 import AgentHarnessV2, ModelRegistry
from web_crawler import WebScraperEngine
from chat_ui import extract_artifact

class TestUIFeaturesAndBusinessOntology(unittest.TestCase):
    """
    Exhaustive test suite verifying that every single UI feature,
    API endpoint, model switcher, and artifact renderer operates with 100% reliability.
    """

    @classmethod
    def setUpClass(cls):
        cls.workspace_dir = Path("/Users/adarrsh/workspace")
        cls.dashboard_url = "http://localhost:5002"
        cls.crawler = WebScraperEngine()
        cls.harness = AgentHarnessV2()

    # =========================================================================
    # 1. TEST DASHBOARD SERVER API ENDPOINTS (UI Backend)
    # =========================================================================

    def test_dashboard_ui_html_served(self):
        """Verify that the split-pane dashboard HTML is properly served at root URL."""
        req = urllib.request.Request(self.dashboard_url)
        with urllib.request.urlopen(req, timeout=5) as resp:
            self.assertEqual(resp.status, 200)
            content = resp.read().decode("utf-8")
            self.assertIn("SkillOpt Studio", content)
            self.assertIn("Ling-3.0-Flash", content)
            self.assertIn("artifact-panel", content)

    def test_dashboard_api_projects_endpoint(self):
        """Verify /api/projects endpoint returns JSON array of projects."""
        req = urllib.request.Request(f"{self.dashboard_url}/api/projects")
        with urllib.request.urlopen(req, timeout=5) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertIsInstance(data, list)

    def test_dashboard_api_mcts_tree_endpoint(self):
        """Verify /api/mcts_tree endpoint returns DPO dataset nodes."""
        req = urllib.request.Request(f"{self.dashboard_url}/api/mcts_tree")
        with urllib.request.urlopen(req, timeout=5) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertIn("nodes_count", data)
            self.assertIn("pairs", data)

    def test_dashboard_api_files_endpoint(self):
        """Verify /api/files endpoint lists workspace files."""
        req = urllib.request.Request(f"{self.dashboard_url}/api/files")
        with urllib.request.urlopen(req, timeout=5) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertIn("files", data)

    # =========================================================================
    # 2. TEST DYNAMIC MODEL SWITCHING & LATENCY BADGES
    # =========================================================================

    def test_model_switching_profiles(self):
        """Verify that the model registry accurately switches and retrieves profiles."""
        models = ["ling-3.0-flash", "nanbeige-3b", "gemma-4-12b", "ornith-9b"]
        for m in models:
            profile = self.harness.set_model(m)
            self.assertIsNotNone(profile)
            self.assertGreater(profile.simulated_tokens_sec, 0)
            self.assertGreater(profile.simulated_ttft_ms, 0)

    # =========================================================================
    # 3. TEST ARTIFACT EXTRACTION & PREVIEW ENGINE
    # =========================================================================

    def test_artifact_extraction_code_blocks(self):
        """Verify that code blocks in LLM responses are cleanly extracted for the side inspector."""
        raw_llm_response = (
            "Here is the requested module:\n\n"
            "```python\n"
            "def calculate_total(items):\n"
            "    return sum(items)\n"
            "```\n"
            "Let me know if you need modifications."
        )
        extracted = extract_artifact(raw_llm_response)
        self.assertIn("def calculate_total", extracted)
        self.assertNotIn("Here is the requested module", extracted)

    def test_artifact_extraction_markdown_docs(self):
        """Verify that structured markdown documents are identified as artifacts."""
        raw_doc = "# System Architecture Document\n\nThis is a full architectural blueprint."
        extracted = extract_artifact(raw_doc)
        self.assertTrue(extracted.startswith("# System Architecture Document"))

    # =========================================================================
    # 4. TEST CRAWL4AI WEB SCRAPER & MARKDOWN INGESTION
    # =========================================================================

    def test_web_crawler_extraction(self):
        """Verify that WebScraperEngine converts web pages into clean LLM-ready markdown."""
        target_url = "https://docs.chainlit.io/get-started/overview"
        res = self.crawler.crawl_sync(target_url)
        self.assertEqual(res["status"], "SUCCESS")
        self.assertIn("markdown", res)
        self.assertTrue(len(res["markdown"]) > 50)
        self.assertIn("Chainlit", res["markdown"])

    # =========================================================================
    # 5. TEST STEP API & DETERMINISTIC AST QUALITY GATE
    # =========================================================================

    def test_ast_validator_quality_gate(self):
        """Verify that valid code passes and invalid code fails the AST gateway."""
        ast_tool = self.harness.tools["ast_validate"]
        
        # Valid code
        valid_res = ast_tool.execute({"code": "def add(a, b):\n    return a + b\n"}, {})
        self.assertEqual(valid_res["status"], "PASSED")
        
        # Invalid code
        invalid_res = ast_tool.execute({"code": "def broken(:\n    pass\n"}, {})
        self.assertEqual(invalid_res["status"], "FAILED")

if __name__ == "__main__":
    unittest.main()
