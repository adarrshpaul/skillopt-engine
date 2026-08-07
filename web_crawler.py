import re
import time
import json
import urllib.request
import asyncio
from typing import Dict, Any, Optional

class WebScraperEngine:
    """
    High-performance, LLM-ready web crawling and markdown extraction engine.
    Uses Crawl4AI when available in an async loop, with a resilient pure-python streaming fallback.
    """
    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 SkillOptAgent/2.4"
        }

    async def crawl_async(self, url: str) -> Dict[str, Any]:
        """Asynchronously crawls a web page and returns clean Markdown."""
        start_time = time.time()
        try:
            from crawl4ai import AsyncWebCrawler
            async with AsyncWebCrawler(verbose=False) as crawler:
                result = await crawler.arun(url=url)
                return {
                    "url": url,
                    "status": "SUCCESS",
                    "engine": "crawl4ai",
                    "markdown": result.markdown,
                    "title": result.metadata.get("title", url),
                    "duration_sec": round(time.time() - start_time, 2)
                }
        except Exception:
            return self._crawl_fallback(url, start_time)

    def crawl_sync(self, url: str) -> Dict[str, Any]:
        """Synchronous crawler entry point for agent tools and HTTP servers."""
        start_time = time.time()
        # Fast resilient fallback avoids thread event loop issues
        return self._crawl_fallback(url, start_time)

    def _crawl_fallback(self, url: str, start_time: float) -> Dict[str, Any]:
        try:
            req = urllib.request.Request(url, headers=self.headers)
            with urllib.request.urlopen(req, timeout=15) as response:
                raw_html = response.read().decode('utf-8', errors='ignore')
                
            title_match = re.search(r'<title>(.*?)</title>', raw_html, re.IGNORECASE | re.DOTALL)
            title = title_match.group(1).strip() if title_match else url
            
            # Strip script, style, nav, footer
            clean_html = re.sub(r'<script.*?</script>', '', raw_html, flags=re.DOTALL | re.IGNORECASE)
            clean_html = re.sub(r'<style.*?</style>', '', clean_html, flags=re.DOTALL | re.IGNORECASE)
            clean_html = re.sub(r'<svg.*?</svg>', '', clean_html, flags=re.DOTALL | re.IGNORECASE)
            
            # Convert headings & formatting to clean markdown
            md = clean_html
            md = re.sub(r'<h1[^>]*>(.*?)</h1>', r'\n# \1\n', md, flags=re.IGNORECASE)
            md = re.sub(r'<h2[^>]*>(.*?)</h2>', r'\n## \1\n', md, flags=re.IGNORECASE)
            md = re.sub(r'<h3[^>]*>(.*?)</h3>', r'\n### \1\n', md, flags=re.IGNORECASE)
            md = re.sub(r'<p[^>]*>(.*?)</p>', r'\n\1\n', md, flags=re.IGNORECASE)
            md = re.sub(r'<li[^>]*>(.*?)</li>', r'\n- \1', md, flags=re.IGNORECASE)
            md = re.sub(r'<code[^>]*>(.*?)</code>', r'`\1`', md, flags=re.IGNORECASE)
            md = re.sub(r'<a\s+[^>]*href=["\'](.*?)["\'][^>]*>(.*?)</a>', r'[\2](\1)', md, flags=re.IGNORECASE)
            md = re.sub(r'<[^>]+>', ' ', md)
            
            # Collapse whitespace
            md = re.sub(r'[ \t]+', ' ', md)
            md = re.sub(r'\n\s*\n+', '\n\n', md).strip()
            
            if len(md) > 15000:
                md = md[:15000] + "\n\n... [Content truncated for LLM Context Compaction]"

            return {
                "url": url,
                "status": "SUCCESS",
                "engine": "resilient_html2md",
                "title": title,
                "markdown": f"# {title}\n\n> Source: {url}\n\n{md}",
                "duration_sec": round(time.time() - start_time, 2)
            }
        except Exception as e:
            return {
                "url": url,
                "status": "ERROR",
                "engine": "error_handler",
                "title": "Failed to crawl",
                "error": str(e),
                "markdown": f"# Error Crawling URL\n\nCould not fetch `{url}`: {e}",
                "duration_sec": round(time.time() - start_time, 2)
            }

if __name__ == "__main__":
    crawler = WebScraperEngine()
    test_url = "https://docs.chainlit.io/get-started/overview"
    print(f"🕷️ Testing WebScraperEngine on: {test_url}")
    res = crawler.crawl_sync(test_url)
    print(f"Status: {res['status']} | Duration: {res['duration_sec']}s | Title: {res['title']}")
