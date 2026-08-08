"""
Model Context Protocol (MCP) Server Manager
Discovers, builds, registers, and executes stdio JSON-RPC tool calls against local MCP servers.
"""
import os
import sys
import json
import subprocess
from typing import Dict, List, Any, Optional
from pathlib import Path

class MCPManager:
    def __init__(self, workspace_dir: str = "/Users/adarrsh/workspace"):
        self.workspace_dir = Path(workspace_dir)

    def list_servers(self) -> List[Dict[str, Any]]:
        """Scans the workspace directory for files matching *_server.py (excluding test files)."""
        servers = []
        for p in self.workspace_dir.glob("*_server.py"):
            if p.name.startswith("test_"):
                continue
            if "dashboard_server" in p.name or "steer_server" in p.name:
                continue
            name = p.stem.replace("_server", "")
            servers.append({
                "name": name,
                "file": p.name,
                "path": str(p),
                "status": "READY"
            })
        return sorted(servers, key=lambda x: x["name"])

    def create_server(self, server_name: str) -> Dict[str, Any]:
        """Uses mcp_builder.py to build and verify a new MCP server."""
        from mcp_builder import build_and_verify_mcp_server
        success = build_and_verify_mcp_server(server_name, str(self.workspace_dir))
        return {
            "name": server_name,
            "status": "PASSED" if success else "FAILED",
            "server_file": f"{server_name}_server.py",
            "test_file": f"test_{server_name}_server.py"
        }

    def execute_jsonrpc(self, server_name: str, method: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Executes a JSON-RPC request against an MCP server script.
        Methods: 'tools/list' or 'tools/call'
        """
        server_file = self.workspace_dir / f"{server_name}_server.py"
        if not server_file.exists():
            return {"error": f"MCP server '{server_name}_server.py' not found."}

        payload = {
            "method": method,
            "params": params or {}
        }
        json_req = json.dumps(payload)

        # Escape the JSON request safely for embedding in Python source
        escaped_json = json.dumps(json_req)  # double-serialize: produces a quoted Python string literal

        code_runner = (
            f"import json, sys\n"
            f"from {server_name}_server import MCPServer\n"
            f"srv = MCPServer('{server_name}')\n"
            f"print(srv.handle_request({escaped_json}))\n"
        )

        try:
            proc = subprocess.run(
                [sys.executable, "-c", code_runner],
                cwd=str(self.workspace_dir),
                capture_output=True,
                text=True,
                timeout=10
            )
            if proc.returncode != 0:
                return {"error": proc.stderr.strip() or "Process execution failed"}
            
            return json.loads(proc.stdout.strip())
        except Exception as e:
            return {"error": str(e)}

if __name__ == "__main__":
    mgr = MCPManager()
    print("Available MCP Servers:", mgr.list_servers())
