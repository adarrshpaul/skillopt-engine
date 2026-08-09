import sys
import os
import json
import subprocess

# Add workspace to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from orchestrator import run_task_graph

def main():
    print("=============================================")
    print(" SWE-Bench Lite Adapter (SkillOpt Engine)")
    print("=============================================")
    
    # Mock pulling a SWE-bench task for demonstration
    swe_task = {
        "instance_id": "django__django-11422",
        "problem_statement": "Add a tracking flag to autoreload to track changes in manage.py. This should automatically restart the server when manage.py is edited.",
        "repo": "django/django",
        "base_commit": "1a2b3c4d"
    }
    
    print(f"📦 Loaded SWE-Bench Task: {swe_task['instance_id']}")
    print(f"📝 Problem Statement: {swe_task['problem_statement']}")
    
    # In a real environment, we would git clone the repo here.
    # For now, we just pass the goal to the orchestrator to test the pipeline.
    
    try:
        print("\n🚀 Handing off to SkillOpt Orchestrator...\n")
        run_task_graph(swe_task["problem_statement"])
        print("\n✅ SWE-Bench Adapter Run Complete.")
    except Exception as e:
        print(f"\n❌ Benchmark Run Failed: {e}")

if __name__ == "__main__":
    main()
