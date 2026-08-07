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
    Playwright End-to-End Automated UI Test Suite.
    Verifies every UI component, interaction, model switcher, and artifact preview.
    """

    @classmethod
    def setUpClass(cls):
        cls.target_url = "http://localhost:8900"
        if not PLAYWRIGHT_AVAILABLE:
            raise unittest.SkipTest("Playwright is not available in the current environment.")

    def test_e2e_full_workflow_automation(self):
        """Automates full user flow across model switching, crawling, and artifact review."""
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(viewport={"width": 1440, "height": 900})
            page = context.new_page()

            print(f"\n🌐 [Playwright] Navigating to {self.target_url}...")
            page.goto(self.target_url, timeout=10000)
            page.wait_for_load_state("domcontentloaded")

            # 1. Verify Brand & Navigation Loaded
            brand_text = page.locator(".brand-text").inner_text()
            self.assertEqual(brand_text, "SkillOpt Studio")
            print("   ✅ Brand & Header verified.")

            # 2. Test Model Switching
            print("   🎛️ [Playwright] Testing Model Switcher Cards...")
            page.click(".model-card[data-model='nanbeige-3b']")
            time.sleep(0.2)
            active_status = page.locator("#activeModelStatus").inner_text()
            self.assertIn("Nanbeige", active_status)
            print("   ✅ Switched to Nanbeige 4.2-3B successfully.")

            page.click(".model-card[data-model='ling-3.0-flash']")
            time.sleep(0.2)
            active_status = page.locator("#activeModelStatus").inner_text()
            self.assertIn("Ling-3.0-Flash", active_status)
            print("   ✅ Switched back to Ling-3.0-Flash (Fastest).")

            # 3. Test Sending a Prompt
            print("   💬 [Playwright] Sending interactive prompt...")
            prompt_input = page.locator("#userInput")
            prompt_input.fill("Write an async redis caching wrapper with ttl")
            page.click("#sendButton")

            # Wait for assistant response and tool card resolution
            page.wait_for_selector("text=Called 1 tool", timeout=10000)
            tool_text = page.locator(".tool-card .tool-header").last.inner_text()
            self.assertIn("Called 1 tool", tool_text)
            print(f"   ✅ Tool execution card rendered: '{tool_text.strip()}'.")

            # 4. Verify Artifact Rendered on Right Split Pane
            artifact_title = page.locator("#artifactTitle").inner_text()
            self.assertTrue(len(artifact_title) > 0)
            print(f"   ✅ Artifact panel loaded: '{artifact_title}'.")

            # 5. Test Preview vs Code Mode Toggle
            print("   📄 [Playwright] Testing Preview vs Code mode toggling...")
            page.click("#btnCode")
            code_visible = page.is_visible("#artifactRawCode")
            self.assertTrue(code_visible)
            print("   ✅ Switched to Code view mode.")

            page.click("#btnPreview")
            preview_visible = page.is_visible("#artifactRendered")
            self.assertTrue(preview_visible)
            print("   ✅ Switched back to Preview Markdown mode.")

            # 6. Test Live Web Crawl starter
            print("   🕷️ [Playwright] Testing live Crawl4AI web crawl...")
            prompt_input.fill("https://docs.chainlit.io/get-started/overview")
            page.click("#sendButton")

            # Wait for crawl response
            time.sleep(1.5)
            crawled_doc_name = page.locator(".tool-doc-chip .doc-name").last.inner_text()
            self.assertTrue(len(crawled_doc_name) > 0)
            print(f"   ✅ Crawled and rendered web artifact: '{crawled_doc_name}'.")

            browser.close()
            print("🎉 [Playwright] Full UI test automation completed with 100% success!\n")

if __name__ == "__main__":
    unittest.main()
