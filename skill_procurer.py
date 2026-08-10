import os
import re
import getpass
import requests
from bs4 import BeautifulSoup
from typing import List, Dict, Any, Tuple

class SkillProcurer:
    """Just-In-Time Skill Procurement pipeline for the SkillOpt Engine."""
    
    def __init__(self, skills_dir: str = "skills"):
        self.skills_dir = skills_dir
        if not os.path.exists(self.skills_dir):
            os.makedirs(self.skills_dir)
            
        # Common integration keywords that trigger skill procurement
        self.integration_keywords = {
            "stripe": "Stripe Webhook/API",
            "aws": "AWS Boto3/CLI",
            "jira": "Jira REST API",
            "slack": "Slack Web API",
            "github": "GitHub API",
            "postgres": "PostgreSQL Schema/Admin"
        }

    def analyze_missing_skills(self, task_graph: List[Dict[str, Any]]) -> List[str]:
        """Analyzes the task graph to find required external skills that are not locally available."""
        required = set()
        
        for task in task_graph:
            description = str(task).lower()
            for kw, skill_name in self.integration_keywords.items():
                if kw in description:
                    required.add(kw)
                    
        # Check what we already have
        missing = []
        for kw in required:
            expected_path = os.path.join(self.skills_dir, f"{kw}_skill.md")
            if not os.path.exists(expected_path):
                missing.append(kw)
                
        return missing

    def get_skill_content(self, task_description: str) -> str:
        """Returns the content of any skills relevant to the task description."""
        content = ""
        description = task_description.lower()
        for kw, skill_name in self.integration_keywords.items():
            if kw in description:
                skill_path = os.path.join(self.skills_dir, f"{kw}_skill.md")
                if os.path.exists(skill_path):
                    with open(skill_path, "r") as f:
                        content += f"\n\n--- SKILL: {skill_name} ---\n" + f.read()
        return content

    def download_skill_silently(self, keyword: str) -> str:
        """
        Scrapes a simulated MCP Marketplace or GitHub to find the skill schema using crawl4ai.
        """
        print(f"\n🔍 [SkillProcurer] Dynamically downloading '{keyword}' skill schema via crawl4ai...", flush=True)
        
        try:
            import asyncio
            from crawl4ai import AsyncWebCrawler
            
            async def _crawl():
                async with AsyncWebCrawler() as crawler:
                    # In a real environment, this would search an MCP marketplace.
                    # For demo purposes, we fetch a raw markdown file from our repo.
                    url = f"https://raw.githubusercontent.com/adarrshpaul/skillopt-engine/main/docs/skills/{keyword}.md"
                    result = await crawler.arun(url=url)
                    if not result.markdown or "404: Not Found" in result.markdown:
                        raise ValueError("No markdown extracted or 404 Not Found")
                    return result.markdown
                    
            content = asyncio.run(_crawl())
        except Exception as e:
            print(f"⚠️ [SkillProcurer] crawl4ai failed ({e}), falling back to mock.", flush=True)
            content = self._generate_mock_skill(keyword)
            
        skill_path = os.path.join(self.skills_dir, f"{keyword}_skill.md")
        with open(skill_path, "w") as f:
            f.write(content)
            
        return content

    def detect_credentials(self, skill_content: str) -> List[str]:
        """Uses Regex to find common API key / Credential requirements in the skill schema."""
        found_creds = set()
        
        # Look for explicit environment variable requests
        env_matches = re.findall(r'os\.environ\.get\([\'"]([A-Z0-9_]+_KEY|[A-Z0-9_]+_TOKEN|[A-Z0-9_]+_SECRET)[\'"]\)', skill_content)
        found_creds.update(env_matches)
        
        # Look for Bearer token documentation
        match = re.search(r'Bearer\s+<([A-Z0-9_]+)>', skill_content, re.IGNORECASE)
        if match:
            found_creds.add(match.group(1))
            
        # Look for explicitly required auth blocks in MCP schema
        auth_matches = re.findall(r'Required Auth:\s*([A-Za-z0-9_]+)', skill_content, re.IGNORECASE)
        found_creds.update(auth_matches)
        
        return list(found_creds)

    def prompt_for_credentials(self, required_keys: List[str], skill_name: str) -> Dict[str, str]:
        """Halts execution to securely ask the user for required credentials."""
        creds = {}
        if not required_keys:
            return creds
            
        print(f"\n" + "="*60, flush=True)
        print(f"🔒 THE CREDENTIAL PROMPT", flush=True)
        print(f"I dynamically downloaded the '{skill_name}' skill. Please provide your credentials to proceed.", flush=True)
        print(f"="*60, flush=True)
        
        for key in required_keys:
            # Check if it's already in the environment
            if os.environ.get(key):
                print(f"✅ Found {key} in environment variables.", flush=True)
                continue
                
            val = getpass.getpass(prompt=f"Enter value for {key}: ")
            creds[key] = val
            os.environ[key] = val # Set it for the subprocesses
            
        print(f"✅ Credentials securely injected. Proceeding with execution...\n", flush=True)
        return creds

    def _generate_mock_skill(self, keyword: str) -> str:
        """Fallback to generate a mock skill if the real scrape fails."""
        mock = f"""# {keyword.title()} Integration Skill

## Overview
This skill provides MCP-compliant tools to interact with the {keyword.title()} API.

## Authentication
Required Auth: {keyword.upper()}_API_KEY
Alternatively, it looks for `os.environ.get("{keyword.upper()}_TEST_SECRET")`.

## Usage
Use this tool to construct valid API requests. Remember to always include the Bearer <{keyword.upper()}_TOKEN> in headers.
"""
        return mock
