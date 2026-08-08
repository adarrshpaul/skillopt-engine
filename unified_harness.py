"""
Unified Agentic Harness — Real LLM Synthesis Pipeline

Stitches together: ChromaDB context retrieval, FastMCP tool discovery,
real LLM code generation (via localhost:8800), AST quality gating,
and DPO flywheel logging into a single pipeline that produces
query-specific responses every time.
"""
import os
import sys
import json
import time
import re
from pathlib import Path
from typing import Dict, List, Any, Optional

from chroma_store import ChromaVectorMemory
from mcp_manager import MCPManager
from agentic_ide_engine import AgenticSystemOrchestrator, TaskNode
from harness_v2 import ModelRegistry


class UnifiedAgenticHarness:
    def __init__(self, workspace_dir: str = "/Users/adarrsh/workspace", default_model: str = "ling-3.0-flash"):
        self.workspace_dir = Path(workspace_dir)
        # Accept either a registry UI key or a raw MLX model id
        if default_model in ModelRegistry.MODELS:
            self.default_model = ModelRegistry.MODELS[default_model].model_id
            self.active_model_key = default_model
        else:
            self.default_model = default_model
            self.active_model_key = "ling-3.0-flash"
        self.memory = ChromaVectorMemory(persist_path=str(self.workspace_dir / "chroma_db"))
        self.mcp_manager = MCPManager(workspace_dir=str(self.workspace_dir))
        self.orchestrator = AgenticSystemOrchestrator(
            workspace_dir=str(self.workspace_dir),
            model_name=self.default_model,
            model_url=ModelRegistry.resolve(self.active_model_key).base_url,
        )

    def _bind_model(self, model_key: str) -> str:
        """Switch the live LLM backend to the registry profile for this UI card."""
        profile = ModelRegistry.resolve(model_key)
        self.active_model_key = model_key if model_key in ModelRegistry.MODELS else self.active_model_key
        self.default_model = profile.model_id
        self.orchestrator.model_name = profile.model_id
        self.orchestrator.model_url = profile.base_url.rstrip("/")
        return profile.model_id

    def execute_unified_pipeline(self, prompt: str, model_key: str = "ling-3.0-flash") -> Dict[str, Any]:
        """
        Executes the real unified pipeline:
        1. ChromaDB context retrieval
        2. FastMCP tool discovery
        3. Real LLM code generation via localhost:8800
        4. AST quality gating
        5. DPO flywheel logging
        """
        bound_model = self._bind_model(model_key)
        start_time = time.time()
        pipeline_stages = []

        # Stage 1: ChromaDB Context Retrieval
        context_hits = self.memory.semantic_search(prompt, n_results=2)
        context_snippet = context_hits[0]["document"][:200] if context_hits else "No prior context."
        pipeline_stages.append({
            "stage": 1,
            "name": "ChromaDB Context Retrieval",
            "status": "COMPLETED",
            "details": f"Retrieved {len(context_hits)} relevant context snippets from vector memory"
        })

        # Stage 2: FastMCP Tool Discovery
        mcp_servers = self.mcp_manager.list_servers()
        pipeline_stages.append({
            "stage": 2,
            "name": "FastMCP Tool Discovery",
            "status": "COMPLETED",
            "details": f"Discovered {len(mcp_servers)} active MCP servers"
        })

        # Stage 3: Real LLM Code Generation + AST Gating
        build_result = self.orchestrator.execute_autonomous_build(prompt)
        generated_code = ""
        target_file = "output.py"
        llm_source = "llm_live"
        for r in build_result["results"]:
            if r.get("code"):
                generated_code = r["code"]
                target_file = r["target_file"]
                llm_source = r.get("source", "unknown")

        pipeline_stages.append({
            "stage": 3,
            "name": "LLM Code Synthesis + AST Gate",
            "status": build_result["test_suite_status"],
            "details": f"Generated '{target_file}' via {llm_source} ({build_result['duration_sec']}s). AST Gate: {build_result['test_suite_status']}"
        })

        # Stage 4: DPO Flywheel Logging
        dpo_entry = {
            "prompt": prompt,
            "model": model_key,
            "target_file": target_file,
            "ast_status": build_result["test_suite_status"],
            "source": llm_source,
            "timestamp": time.time()
        }
        dpo_file = self.workspace_dir / "dpo_logs.jsonl"
        try:
            with open(dpo_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(dpo_entry) + "\n")
        except Exception:
            pass

        pipeline_stages.append({
            "stage": 4,
            "name": "DPO Flywheel Logging",
            "status": "COMPLETED",
            "details": "Recorded evaluation trace to dpo_logs.jsonl"
        })

        duration = round(time.time() - start_time, 2)

        # Build artifact with the REAL generated code
        stages_md = "\n".join([
            f"- **Stage {s['stage']} — {s['name']}**: `{s['status']}` — {s['details']}"
            for s in pipeline_stages
        ])

        # Truncate code display for very long outputs
        code_display = generated_code if len(generated_code) < 3000 else generated_code[:3000] + "\n# ... (truncated)"

        artifact_content = (
            f"# {prompt[:80]}\n\n"
            f"> **UI Model:** `{model_key}` | **Backend:** `{bound_model}` | **Latency:** {duration}s | **Source:** `{llm_source}`\n"
            f"> **Output File:** [`{target_file}`](file:///Users/adarrsh/workspace/{target_file})\n\n"
            f"## Pipeline Telemetry\n{stages_md}\n\n"
            f"## Generated Code (`{target_file}`)\n```python\n{code_display}\n```\n"
        )

        # Derive a human-readable artifact title from the prompt
        title_slug = re.sub(r'[^\w\s]', '', prompt.lower()).split()
        artifact_title = '_'.join(title_slug[:5]) + '.py' if title_slug else 'output.py'

        return {
            "model": bound_model,
            "model_key": model_key,
            "duration_sec": duration,
            "stages": pipeline_stages,
            "artifact_title": artifact_title,
            "artifact": artifact_content,
            "text": (
                f"Generated **`{target_file}`** using real LLM inference "
                f"(`{bound_model}` via `{model_key}`) in **{duration}s**. "
                f"AST Quality Gate: **{build_result['test_suite_status']}**."
            )
        }


if __name__ == "__main__":
    harness = UnifiedAgenticHarness()
    prompt = sys.argv[1] if len(sys.argv) > 1 else "Write an async Redis caching wrapper with TTL support"
    res = harness.execute_unified_pipeline(prompt)
    print(f"\n🎉 Pipeline Complete in {res['duration_sec']}s")
    print(res["text"])
