import os
import subprocess
import time
import sys

MODELS = [
    "nvidia/nemotron-3-ultra-550b-a55b:free",
    "poolside/laguna-s-2.1:free",
    "nvidia/nemotron-3.5-lightning:free",
    "nvidia/nemotron-3-super-120b-a12b:free",
    "cohere/north-mini-code:free",
    "poolside/laguna-xs-2.1:free",
    "nvidia/nemotron-3-nano-30b-a3b:free",
    "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
    "google/gemma-4-26b-a4b-it:free",
    "nvidia/nemotron-nano-9b-v2:free",
    "dots-studio/dots-3-note-preview:free",
    "openai/gpt-oss-20b:free",
    "nvidia/nemotron-nano-12b-v2-vl:free",
    "liquid/lfm-2.5-2.6b:free"
]

TASK_PROMPT = "Create a string_helper.py file with a function that reverses a string, and follow STRICT_RULES.md exactly."

def run_benchmark():
    print(f"🚀 Starting Free Model Benchmarks on Orchestrator", flush=True)
    print("=" * 60, flush=True)
    
    results = []
    
    for model in MODELS:
        print(f"\n🧪 Evaluating Model: {model}", flush=True)
        
        # Clean up target file from previous runs
        if os.path.exists("string_helper.py"):
            os.remove("string_helper.py")
        if os.path.exists("harness_checkpoint.json"):
            os.remove("harness_checkpoint.json")
            
        env = os.environ.copy()
        env["PLANNER_ENGINE"] = "openrouter"
        env["PLANNER_URL"] = "https://openrouter.ai/api/v1"
        env["PLANNER_MODEL"] = model
        
        env["REVIEWER_ENGINE"] = "openrouter"
        env["REVIEWER_URL"] = "https://openrouter.ai/api/v1"
        env["REVIEWER_MODEL"] = model
        
        env["CODER_ENGINE"] = "openrouter"
        env["CODER_URL"] = "https://openrouter.ai/api/v1"
        env["CODER_MODEL"] = model
        
        start_time = time.time()
        
        try:
            # We run the orchestrator script
            # We use timeout of 60 seconds so it doesn't hang forever
            proc = subprocess.run(
                [sys.executable, "-u", "orchestrator.py", TASK_PROMPT],
                env=env,
                capture_output=True,
                text=True,
                timeout=600
            )
            duration = round(time.time() - start_time, 2)
            
            gov_pass = "⚠️  [Reporails] Instruction Governance Failed:" not in proc.stdout
            ast_pass = os.path.exists("string_helper.py")
            
            # Additional check to see if the file actually parses
            if ast_pass:
                try:
                    import ast
                    with open("string_helper.py", "r") as f:
                        ast.parse(f.read())
                except Exception:
                    ast_pass = False
                    
            status = "PASSED" if ast_pass else "FAILED"
            if not gov_pass:
                status = "GOV_BLOCKED"
                
            print(f"   ⏱️ Duration: {duration}s | Status: {status}")
            
            # Print a snippet of errors if it failed
            if status != "PASSED":
                print("   [Log Snippet]:")
                lines = [l for l in proc.stdout.split('\n') if 'error' in l.lower() or 'exception' in l.lower()][:3]
                for l in lines:
                    print(f"      {l}")
                    
            results.append({
                "model": model,
                "duration": duration,
                "status": status,
                "gov_pass": gov_pass
            })
            
        except subprocess.TimeoutExpired:
            print(f"   ⏱️ Duration: >600s | Status: TIMEOUT")
            results.append({
                "model": model,
                "duration": 600.0,
                "status": "TIMEOUT",
                "gov_pass": True
            })
        
        # No cooldown needed anymore thanks to MLX hot-swapping
            
    print("\n\n🏆 BENCHMARK LEADERBOARD 🏆")
    print("=" * 70)
    print(f"{'Model':<50} | {'Status':<10} | {'Duration'}")
    print("-" * 70)
    
    # Sort by PASS first, then duration
    results.sort(key=lambda x: (0 if x['status'] == 'PASSED' else 1, x['duration']))
    
    for r in results:
        print(f"{r['model']:<50} | {r['status']:<10} | {r['duration']}s")
        
if __name__ == "__main__":
    run_benchmark()
