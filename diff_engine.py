import json
import argparse
import os
import urllib.request
import urllib.error
from typing import List, Dict

# Import reward function from grpo_trainer
from grpo_trainer import composite_reward

import model_router

class DiffEngine:
    def __init__(self, base_model_url='http://localhost:11434', enhanced_url=None):
        self.base_model_url = base_model_url.rstrip('/')
        self.enhanced_url = (enhanced_url or model_router.get_url("coder")).rstrip('/')
        
    def query_ollama(self, prompt: str, model: str = 'ornith:9b') -> str:
        """
        Queries the base model via Ollama.
        """
        url = f"{self.base_model_url}/api/generate"
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False
        }
        
        try:
            req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), 
                                         headers={'Content-Type': 'application/json'})
            with urllib.request.urlopen(req) as response:
                result = json.loads(response.read().decode('utf-8'))
                return result.get("response", "")
        except Exception as e:
            print(f"Error querying Ollama: {e}")
            return f"Error: {e}"

    def query_enhanced(self, prompt: str) -> str:
        """
        Queries the enhanced model. Falls back to Ollama if unavailable.
        """
        url = f"{self.enhanced_url}/v1/generate"
        payload = {
            "prompt": prompt
        }
        
        try:
            req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), 
                                         headers={'Content-Type': 'application/json'})
            with urllib.request.urlopen(req, timeout=10) as response:
                result = json.loads(response.read().decode('utf-8'))
                return result.get("response", result.get("text", str(result)))
        except (urllib.error.URLError, Exception) as e:
            print(f"Enhanced server unavailable ({e}). Falling back to Ollama.")
            return self.query_ollama(prompt, model='ornith:9b')

    def compute_reward(self, prompt: str, response: str) -> float:
        """
        Computes the composite reward for a given prompt and response.
        """
        return composite_reward(prompt, response)

    def run_comparison(self, prompts: List[str]) -> List[Dict]:
        """
        Runs the comparison between base and enhanced models.
        """
        results = []
        for i, prompt in enumerate(prompts, 1):
            print(f"Processing prompt {i}/{len(prompts)}...")
            
            base_response = self.query_ollama(prompt)
            enhanced_response = self.query_enhanced(prompt)
            
            base_reward = self.compute_reward(prompt, base_response)
            enhanced_reward = self.compute_reward(prompt, enhanced_response)
            
            improvement = enhanced_reward - base_reward
            
            results.append({
                "prompt": prompt,
                "base_response": base_response,
                "enhanced_response": enhanced_response,
                "base_reward": base_reward,
                "enhanced_reward": enhanced_reward,
                "improvement": improvement
            })
            
        return results

    def generate_report(self, results: List[Dict], output_path: str) -> None:
        """
        Generates a markdown report summarizing the comparison.
        """
        if not results:
            print("No results to report.")
            return
            
        avg_base = sum(r['base_reward'] for r in results) / len(results)
        avg_enhanced = sum(r['enhanced_reward'] for r in results) / len(results)
        
        avg_improvement_pct = ((avg_enhanced - avg_base) / avg_base * 100) if avg_base > 0 else 0
        
        os.makedirs(os.path.dirname(os.path.abspath(output_dir := output_path)), exist_ok=True)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write("# Model Comparison Report\n\n")
            
            f.write("## Summary Statistics\n")
            f.write(f"- **Average Base Reward:** {avg_base:.4f}\n")
            f.write(f"- **Average Enhanced Reward:** {avg_enhanced:.4f}\n")
            f.write(f"- **Average Improvement:** {avg_improvement_pct:.2f}%\n\n")
            
            f.write("## Per-Prompt Side-by-Side\n\n")
            
            for i, r in enumerate(results, 1):
                f.write(f"### Prompt {i}\n")
                f.write(f"**Prompt:** {r['prompt']}\n\n")
                
                if r['improvement'] > 0.05:
                    f.write("🎉 **WIN for Enhanced Model**\n\n")
                elif r['improvement'] < -0.05:
                    f.write("⚠️ **LOSS for Enhanced Model**\n\n")
                else:
                    f.write("⚖️ **TIE**\n\n")
                    
                f.write(f"**Base Model (Reward: {r['base_reward']:.4f})**\n")
                f.write(f"```\n{r['base_response']}\n```\n\n")
                
                f.write(f"**Enhanced Model (Reward: {r['enhanced_reward']:.4f})**\n")
                f.write(f"```\n{r['enhanced_response']}\n```\n\n")
                
                f.write("---\n\n")

def main():
    parser = argparse.ArgumentParser(description="Comparison engine for Project Ornith")
    parser.add_argument("--dataset", type=str, required=True, help="Path to the JSONL dataset")
    parser.add_argument("--output", type=str, default=".tasks/done/ornith_vs_enhanced_diff.md", help="Output path for the report")
    parser.add_argument("--num-prompts", type=int, default=20, help="Number of prompts to compare")
    args = parser.parse_args()
    
    if not os.path.exists(args.dataset):
        print(f"Error: Dataset {args.dataset} not found.")
        return
        
    prompts = []
    with open(args.dataset, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                data = json.loads(line)
                if "prompt" in data:
                    prompts.append(data["prompt"])
                if len(prompts) >= args.num_prompts:
                    break
            except json.JSONDecodeError:
                continue
                
    if not prompts:
        print("No prompts found in dataset.")
        return
        
    engine = DiffEngine()
    print(f"Running comparison for {len(prompts)} prompts...")
    results = engine.run_comparison(prompts)
    
    print(f"Generating report at {args.output}")
    engine.generate_report(results, args.output)
    print("Done.")

if __name__ == "__main__":
    main()
