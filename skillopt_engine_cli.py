import os
import sys
import json
import argparse
import subprocess

BANNER = """
================================================================================
🚀 SkillOpt Engine — Master Autonomous AI & Steering Package
   Unified Local AI Coding Stack (MLX + Dual-Layer Steering + DPO Flywheel)
================================================================================
"""

def cmd_serve(args):
    print("🌐 Launching Steerable Inference Server on port 8800...")
    cmd = [sys.executable, "/Users/adarrsh/workspace/steer_server.py", "--port", str(args.port)]
    subprocess.run(cmd)

def cmd_sync(args):
    print("🔄 Syncing latest best_skill.md to IDEs & Agent Runtimes...")
    skill_path = args.skill or "/Users/adarrsh/workspace/skillopt/runs/best_skill.md"
    content = ""
    if os.path.exists(skill_path):
        with open(skill_path) as f:
            content = f.read()
    else:
        content = "# Default SkillOpt Guidelines\n- Always output clean, valid code."
        
    # Sync to Cursor
    with open(os.path.join(os.getcwd(), ".cursorrules"), "w") as f:
        f.write(content)
    print("  ✅ Synced to .cursorrules")

    # Sync to Antigravity
    agy_dir = os.path.join(os.getcwd(), ".agents", "rules")
    os.makedirs(agy_dir, exist_ok=True)
    with open(os.path.join(agy_dir, "skillopt_guidelines.md"), "w") as f:
        f.write(content)
    print("  ✅ Synced to .agents/rules/skillopt_guidelines.md")

def cmd_orchestrate(args):
    from orchestrator import run_task_graph
    run_task_graph(args.goal)

def cmd_mcp(args):
    from mcp_builder import build_and_verify_mcp_server
    build_and_verify_mcp_server(args.name, args.out)

def cmd_self_improve(args):
    from dpo_tree_generator import explore_and_generate_dpo_pairs
    from dpo_train import train_dpo_model
    
    print("\n🌿 [Phase 1/2] Exploring Decision Tree Branches for Ground Truth Verification...")
    explore_and_generate_dpo_pairs(args.task, args.branches)
    
    print("\n🎯 [Phase 2/2] Running DPO LoRA Fine-Tuning Pass...")
    train_dpo_model(args.dataset, args.out, epochs=args.epochs)

def cmd_health(args):
    from auto_coder import handle_test_command
    handle_test_command()

def main():
    print(BANNER)
    parser = argparse.ArgumentParser(description="SkillOpt Engine Unified Master CLI")
    subparsers = parser.add_subparsers(dest="command", help="Available Commands")

    # serve
    serve_p = subparsers.add_parser("serve", help="Launch local Steer Server")
    serve_p.add_argument("--port", type=int, default=8800, help="Port number")

    # sync
    sync_p = subparsers.add_parser("sync", help="Sync skills to Cursor and Antigravity")
    sync_p.add_argument("--skill", type=str, default="", help="Path to best_skill.md")

    # orchestrate
    orch_p = subparsers.add_parser("orchestrate", help="Run Gemma-4 Planner + Ornith Coder task graph")
    orch_p.add_argument("goal", type=str, help="High-level project goal")

    # mcp
    mcp_p = subparsers.add_parser("mcp", help="Scaffold & verify MCP server")
    mcp_p.add_argument("name", type=str, help="Server name prefix")
    mcp_p.add_argument("--out", type=str, default=".", help="Output directory")

    # self-improve
    dpo_p = subparsers.add_parser("self-improve", help="Run Graph DPO tree search + LoRA training pass")
    dpo_p.add_argument("task", type=str, nargs="?", default="Write a python function `is_palindrome(s: str) -> bool` with doctests.", help="Task spec")
    dpo_p.add_argument("--branches", type=int, default=4, help="Branches to explore")
    dpo_p.add_argument("--dataset", type=str, default="/Users/adarrsh/workspace/dpo_graph_dataset.jsonl")
    dpo_p.add_argument("--out", type=str, default="/Users/adarrsh/workspace/dpo_adapters")
    dpo_p.add_argument("--epochs", type=int, default=3)

    # health
    subparsers.add_parser("health", help="Run workspace health check across all Python files")

    args = parser.parse_args()

    commands = {
        "serve": cmd_serve,
        "sync": cmd_sync,
        "orchestrate": cmd_orchestrate,
        "mcp": cmd_mcp,
        "self-improve": cmd_self_improve,
        "health": cmd_health
    }

    if args.command in commands:
        commands[args.command](args)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
