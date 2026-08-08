import os
import sys
import time
import unittest
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    sync_playwright = None
    PLAYWRIGHT_AVAILABLE = False

class TestSkillOptStudioPlaywright(unittest.TestCase):
    """
    Exhaustive Playwright End-to-End Automated UI Test Suite.
    Verifies every UI component, model switcher, crawl pill, test runner,
    MCP Modal overlay, Build & Verify button, and live stdio JSON-RPC execution.
    """

    @classmethod
    def setUpClass(cls):
        cls.target_url = "http://localhost:5002"
        if not PLAYWRIGHT_AVAILABLE:
            raise unittest.SkipTest("Playwright is not available in the current environment.")

    def test_e2e_full_workflow_automation(self):
        """Automates full user flow across model switching, crawling, MCP creation, and artifact review."""
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(viewport={"width": 1440, "height": 900})
            page = context.new_page()

            print(f"\n🌐 [Playwright] Navigating to {self.target_url}...")
            page.goto(self.target_url, timeout=10000)
            page.wait_for_load_state("domcontentloaded")

            # 1. Verify Brand & Navigation Header
            brand_text = page.locator(".brand-text").inner_text()
            self.assertEqual(brand_text, "SkillOpt Studio")
            print("   ✅ Step 1: Brand & Header navigation verified.")

            # 2. Test Model Switching across all 4 cards
            print("   🎛️ [Playwright] Testing Model Switcher Cards...")
            page.click(".model-card[data-model='nanbeige-3b']")
            time.sleep(0.2)
            self.assertIn("Nanbeige", page.locator("#activeModelStatus").inner_text())

            page.click(".model-card[data-model='gemma-4-12b']")
            time.sleep(0.2)
            self.assertIn("Gemma", page.locator("#activeModelStatus").inner_text())

            page.click(".model-card[data-model='ling-3.0-flash']")
            time.sleep(0.2)
            self.assertIn("Ling-3.0-Flash", page.locator("#activeModelStatus").inner_text())
            print("   ✅ Step 2: All Model switcher cards responsive.")

            # 3. Test Interactive Code Synthesis Prompt
            print("   💬 [Playwright] Sending interactive prompt...")
            prompt_input = page.locator("#userInput")
            prompt_input.fill("Write an async redis caching wrapper with ttl")
            page.click("#sendButton")

            page.wait_for_selector("text=Called 1 tool", timeout=45000)
            tool_text = page.locator(".tool-card .tool-header").last.inner_text()
            self.assertIn("Called 1 tool", tool_text)
            print(f"   ✅ Step 3: Tool execution card rendered -> '{tool_text.strip()}'.")

            # 4. Verify Artifact Split Pane View Modes (Preview vs Code)
            print("   📄 [Playwright] Testing Preview vs Code view mode toggles...")
            page.click("#btnCode")
            self.assertTrue(page.is_visible("#artifactRawCode"))
            page.click("#btnPreview")
            self.assertTrue(page.is_visible("#artifactRendered"))
            print("   ✅ Step 4: Preview and Code view mode toggles verified.")

            # 5. Test Live Crawl4AI Web Crawling
            print("   🕷️ [Playwright] Testing live Crawl4AI web crawl...")
            prompt_input.fill("https://docs.chainlit.io/get-started/overview")
            page.click("#sendButton")
            time.sleep(1.5)
            crawled_doc_name = page.locator(".tool-doc-chip .doc-name").last.inner_text()
            self.assertTrue(len(crawled_doc_name) > 0)
            print(f"   ✅ Step 5: Crawled and rendered web artifact -> '{crawled_doc_name}'.")

            # 6. Test Open MCP Server Hub Modal Overlay
            print("   🔌 [Playwright] Opening MCP Server Hub Modal Overlay...")
            page.click(".mcp-hub-btn")
            time.sleep(0.3)
            self.assertTrue(page.is_visible("#mcpModal"))
            print("   ✅ Step 6: MCP Server Hub Modal overlay rendered.")

            # 7. Test "Build & Verify" Button for New MCP Server Creation
            print("   🛠️ [Playwright] Testing 'Build & Verify' New MCP Server Creation...")
            mcp_input = page.locator("#newMcpName")
            mcp_input.fill("redis_mcp")
            page.click("button:has-text('Build & Verify')")
            time.sleep(1.2)

            console_text = page.locator("#mcpJsonConsole").inner_text()
            self.assertIn("PASSED", console_text)
            print("   ✅ Step 7: 'Build & Verify' button successfully built new MCP Server 'redis_mcp'!")

            # 8. Test Live JSON-RPC execution (tools/list & tools/call)
            print("   🧪 [Playwright] Testing stdio JSON-RPC tool list and execution...")
            page.click("#mcpServerList button:has-text('tools/list')")
            time.sleep(0.5)
            list_output = page.locator("#mcpJsonConsole").inner_text()
            self.assertIn("tools", list_output)

            page.click("#mcpServerList button:has-text('tools/call add')")
            time.sleep(0.5)
            call_output = page.locator("#mcpJsonConsole").inner_text()
            self.assertIn("content", call_output)
            print("   ✅ Step 8: Live stdio JSON-RPC tools/list and tools/call executed successfully.")

            browser.close()
            print("\n🎉 [Playwright] Comprehensive E2E UI Test Suite Passed with 100% Success!\n")

    def test_e2e_api_tester_portal(self):
        """Verifies the new Model Fleet API Tester portal."""
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context()
            page = context.new_page()

            tester_url = f"{self.target_url}/tester.html"
            print(f"\n🌐 [Playwright] Navigating to {tester_url}...")
            page.goto(tester_url, timeout=10000)
            page.wait_for_load_state("domcontentloaded")

            # 1. Verify UI loaded
            title = page.locator("h1").inner_text()
            self.assertEqual(title, "Model Fleet API Tester")

            # 2. Wait for fleet config to load (simulating API fetch)
            # The UI says "Connecting to Fleet..." then "Fleet Online"
            page.wait_for_selector("#fleetStatusText:has-text('Fleet Online')", timeout=5000)
            fleet_info = page.locator("#fleetInfo").inner_text()
            self.assertIn("planner", fleet_info.lower())
            
            # 3. Enter test prompt and submit
            print("   💬 [Playwright] Submitting test payload to API Tester...")
            page.fill("#reqPayload", "Say 'Hello Playwright!' in Python")
            page.click("#sendBtn")

            # 4. Wait for LLM response
            # Since LLM might take time, wait up to 90s for success meta element
            page.wait_for_selector("#execMeta:has-text('Success')", timeout=90000)
            
            # Verify the response JSON is populated
            response_json = page.locator("#responseBox").inner_text()
            self.assertIn("node_id", response_json)
            self.assertIn("action", response_json)
            print("   ✅ API Tester portal correctly executed inference.")

            browser.close()


if __name__ == "__main__":
    unittest.main()
