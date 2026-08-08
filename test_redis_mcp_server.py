"""
Unit Tests for Generated MCP Server
"""
import unittest
import json
from redis_mcp_server import MCPServer

class TestMCPServer(unittest.TestCase):
    def setUp(self):
        self.server = MCPServer()

    def test_list_tools(self):
        response = json.loads(self.server.handle_request('{"method": "tools/list"}'))
        self.assertIn("result", response)
        tools = response["result"]["tools"]
        tool_names = [t["name"] for t in tools]
        self.assertIn("add", tool_names)
        self.assertIn("echo", tool_names)

    def test_call_add_tool(self):
        req = json.dumps({
            "method": "tools/call",
            "params": {"name": "add", "arguments": {"a": 5, "b": 10}}
        })
        response = json.loads(self.server.handle_request(req))
        self.assertIn("result", response)
        res_text = response["result"]["content"][0]["text"]
        self.assertEqual(res_text, "15")

if __name__ == "__main__":
    unittest.main()
