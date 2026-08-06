#!/usr/bin/env python3
"""
Automated MCP Testing Engine (No external dependencies)
Spawns the MCP servers via subprocess and sends JSON-RPC to stdin,
verifying they are alive and returning correct structures.
"""
import subprocess
import json
import time
import sys

def test_mcp_server(name, command):
    print(f"\n--- Testing {name} ---")
    try:
        # Start the MCP server process
        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            shell=True
        )
        
        # 1. Send initialize
        init_req = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test-runner", "version": "1.0"}
            }
        }
        
        process.stdin.write(json.dumps(init_req) + "\n")
        process.stdin.flush()
        
        # Read initialization response
        init_resp_str = process.stdout.readline()
        init_resp = json.loads(init_resp_str)
        if "result" in init_resp and "serverInfo" in init_resp["result"]:
            print(f"[+] Initialize successful! Server: {init_resp['result']['serverInfo']['name']}")
        else:
            print(f"[-] Initialize failed: {init_resp}")
            process.terminate()
            return False
            
        # 2. Send tools/list
        tools_req = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/list",
            "params": {}
        }
        process.stdin.write(json.dumps(tools_req) + "\n")
        process.stdin.flush()
        
        # Read tools list response
        tools_resp_str = process.stdout.readline()
        tools_resp = json.loads(tools_resp_str)
        if "result" in tools_resp and "tools" in tools_resp["result"]:
            tool_names = [t["name"] for t in tools_resp["result"]["tools"]]
            print(f"[+] Tools found: {', '.join(tool_names)}")
            print(f"\n[+] SUCCESS: {name} MCP responded correctly.")
            process.terminate()
            return True
        else:
            print(f"[-] Tools list failed: {tools_resp}")
            process.terminate()
            return False
            
    except Exception as e:
        print(f"[-] ERROR connecting to {name}: {e}")
        return False

def main():
    print("Starting Automated MCP Validations...")
    coord_success = test_mcp_server("Workspace Coordinator", "/Users/adarrsh/workspace/run_coord_mcp.sh")
    ix_success = test_mcp_server("Siemens iX", "/Users/adarrsh/workspace/run_siemens_ix_mcp.sh")
    
    if coord_success and ix_success:
        print("\n--- All Tests Complete: SUCCESS ---")
        sys.exit(0)
    else:
        print("\n--- All Tests Complete: FAILURE ---")
        sys.exit(1)

if __name__ == "__main__":
    main()
