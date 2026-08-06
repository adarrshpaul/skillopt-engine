import json
import os
import argparse
from typing import List, Dict

class PromptOptimizer:
    def __init__(self, prompt_bank_path: str = 'skills/prompt_bank.jsonl', system_prompts_dir: str = 'skills/system_prompts/'):
        self.prompt_bank_path = prompt_bank_path
        self.system_prompts_dir = system_prompts_dir
        self.prompt_bank = self._load_prompt_bank()
        self.system_prompts = self._load_system_prompts()
        
    def _load_prompt_bank(self) -> List[Dict]:
        bank = []
        if os.path.exists(self.prompt_bank_path):
            try:
                with open(self.prompt_bank_path, 'r') as f:
                    for line in f:
                        if line.strip():
                            bank.append(json.loads(line))
            except Exception as e:
                print(f"Error loading prompt bank: {e}")
        return bank

    def _load_system_prompts(self) -> Dict[str, str]:
        prompts = {}
        if os.path.exists(self.system_prompts_dir):
            try:
                for filename in os.listdir(self.system_prompts_dir):
                    if filename.endswith('.txt'):
                        task_type = filename[:-4]
                        with open(os.path.join(self.system_prompts_dir, filename), 'r') as f:
                            prompts[task_type] = f.read().strip()
            except Exception as e:
                print(f"Error loading system prompts: {e}")
        return prompts

    def classify_task(self, prompt: str) -> str:
        prompt_lower = prompt.lower()
        if any(word in prompt_lower for word in ['create', 'build', 'implement', 'write', 'scaffold', 'generate']):
            return 'code_generation'
        elif any(word in prompt_lower for word in ['fix', 'error', 'bug', 'debug', 'broken', 'failing', 'crash']):
            return 'debugging'
        elif any(word in prompt_lower for word in ['explain', 'how', 'why', 'what is', 'describe']):
            return 'explanation'
        elif any(word in prompt_lower for word in ['run', 'execute', 'command', 'terminal', 'shell', 'install']):
            return 'shell_command'
        elif any(word in prompt_lower for word in ['edit', 'modify', 'update', 'change', 'replace']):
            return 'file_edit'
        else:
            return 'general'

    def get_system_prompt(self, task_type: str) -> str:
        if task_type in self.system_prompts:
            return self.system_prompts[task_type]
            
        defaults = {
            'code_generation': 'You are an expert software engineer. Emphasize writing complete, working code with error handling. Think step by step.',
            'debugging': 'You are an expert debugging assistant. Emphasize reading error messages carefully, identifying root cause, providing fix.',
            'explanation': 'You are an expert teacher. Explain concepts clearly, concisely, and step-by-step.',
            'shell_command': 'You are a system administrator. Provide clear, accurate, and safe shell commands.',
            'file_edit': 'You are an expert developer. Make precise and correct modifications to existing files.',
            'general': 'You are a helpful and capable AI assistant. Answer carefully and logically.'
        }
        return defaults.get(task_type, defaults['general'])

    def get_few_shot_exemplars(self, task_type: str, n: int = 2) -> List[Dict]:
        matching = [item for item in self.prompt_bank if item.get('task_type') == task_type]
        return matching[:n]

    def build_chain_of_thought(self, prompt: str) -> str:
        return f"Think through this step by step:\n1. Understand what is being asked\n2. Plan the approach\n3. Implement the solution\n4. Verify correctness\n\nTask: {prompt}"

    def optimize(self, prompt: str, context: str = '') -> str:
        task_type = self.classify_task(prompt)
        sys_prompt = self.get_system_prompt(task_type)
        exemplars = self.get_few_shot_exemplars(task_type)
        
        optimized = []
        optimized.append(f"<system>\n{sys_prompt}\n</system>")
        
        if context:
            optimized.append(f"<context>\n{context}\n</context>")
            
        if exemplars:
            optimized.append("<examples>")
            for ex in exemplars:
                optimized.append(f"Input: {ex.get('input', '')}\nOutput: {ex.get('output', '')}")
            optimized.append("</examples>")
            
        cot_prompt = self.build_chain_of_thought(prompt)
        optimized.append(f"<task>\n{cot_prompt}\n</task>")
        
        return "\n\n".join(optimized)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Adaptive prompt engineering layer.')
    parser.add_argument('--prompt', type=str, required=True, help='The prompt to optimize')
    parser.add_argument('--context', type=str, default='', help='Optional context')
    args = parser.parse_args()
    
    optimizer = PromptOptimizer()
    optimized_prompt = optimizer.optimize(args.prompt, args.context)
    print(optimized_prompt)
