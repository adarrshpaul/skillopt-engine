import os
import sys
import json
import argparse
import subprocess

WELCOME_BANNER = """
============================================================
🤖 AutoCoder Developer Bundle v1.0
   Local Developer Assistant & Project Generator
============================================================
"""

def handle_mcp_command(name: str, out_dir: str):
    from mcp_builder import build_and_verify_mcp_server
    print(f"\n🚀 Creating verified MCP Server starter: '{name}'...")
    success = build_and_verify_mcp_server(name, out_dir)
    if success:
        print(f"\n✨ Success! Your MCP server '{name}' is ready to use.")
    else:
        print(f"\n⚠️ Creation completed with verification warnings.")

def handle_plan_command(goal: str):
    from orchestrator import run_task_graph
    run_task_graph(goal)

def handle_test_command():
    print("\n🔍 Running Workspace Health Check...")
    python_files = [f for f in os.listdir(".") if f.endswith(".py")]
    print(f"   Found {len(python_files)} Python files to inspect.")
    
    passed = 0
    failed = 0
    for f in python_files:
        res = subprocess.run([sys.executable, "-m", "py_compile", f], capture_output=True, text=True)
        if res.returncode == 0:
            passed += 1
        else:
            failed += 1
            print(f"   ❌ Syntax Warning in {f}: {res.stderr.strip()}")
            
    print(f"\n📊 Health Check Summary: {passed} Passed, {failed} Failed.")
    if failed == 0:
        print("🎉 Workspace is healthy and clean!")

def main():
    print(WELCOME_BANNER)
    parser = argparse.ArgumentParser(description="AutoCoder Developer Bundle")
    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # MCP command
    mcp_parser = subparsers.add_parser("mcp", help="Generate a verified MCP server starter")
    mcp_parser.add_argument("name", type=str, help="Server name prefix")
    mcp_parser.add_argument("--out", type=str, default=".", help="Output directory")

    # Plan command
    plan_parser = subparsers.add_parser("plan", help="Decompose a project goal into a task graph")
    plan_parser.add_argument("goal", type=str, help="High-level goal description")

    # Health check test command
    subparsers.add_parser("test", help="Run workspace health check on Python files")

    args = parser.parse_args()

    if args.command == "mcp":
        handle_mcp_command(args.name, args.out)
    elif args.command == "plan":
        handle_plan_command(args.goal)
    elif args.command == "test":
        handle_test_command()
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
