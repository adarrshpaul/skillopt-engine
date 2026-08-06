import json
import argparse
import os
import re

import torch
from datasets import Dataset
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import LoraConfig, get_peft_model
from trl import GRPOTrainer, GRPOConfig

def format_reward(response: str) -> float:
    """
    Reward function to check for proper markdown and code formatting.
    Returns 0.0 to 1.0.
    """
    score = 0.0
    if "```" in response:
        score += 0.5
    if re.search(r'\*\*.*?\*\*', response) or re.search(r'#+\s', response):
        score += 0.5
    if score == 0.0 and len(response.strip()) > 0:
        score = 0.2 # Some base score for text
    return min(1.0, score)

def completeness_reward(prompt: str, response: str) -> float:
    """
    Reward function to check if the response addresses key terms from the prompt.
    Returns 0.0 to 1.0.
    """
    prompt_words = set(re.findall(r'\b\w+\b', prompt.lower()))
    important_words = {w for w in prompt_words if len(w) > 4}
    
    if not important_words:
        return 1.0
        
    response_lower = response.lower()
    matches = sum(1 for w in important_words if w in response_lower)
    
    return matches / len(important_words)

def conciseness_reward(response: str) -> float:
    """
    Reward function to penalize overly verbose responses (>2000 chars) 
    and too-short ones (<50 chars).
    Returns 0.0 to 1.0.
    """
    length = len(response)
    if length < 50:
        return max(0.0, length / 50.0)
    elif length > 2000:
        penalty = (length - 2000) / 1000.0
        return max(0.0, 1.0 - penalty)
    return 1.0

def code_quality_reward(response: str) -> float:
    """
    Reward function to check for code quality signals in code blocks.
    Returns 0.0 to 1.0.
    """
    if "```" not in response:
        return 0.5 # Neutral if no code
        
    code_blocks = re.findall(r'```.*?\n(.*?)```', response, re.DOTALL)
    if not code_blocks:
        return 0.5
        
    score = 0.0
    for block in code_blocks:
        if "def " in block or "class " in block:
            score += 0.4
        if "try:" in block or "except " in block or "raise " in block:
            score += 0.3
        if '"""' in block or "'''" in block or "#" in block:
            score += 0.3
            
    return min(1.0, score / max(1, len(code_blocks)))

def composite_reward(prompt: str, response: str) -> float:
    """
    Reward function that computes a weighted average of all rewards.
    """
    r_format = format_reward(response)
    r_complete = completeness_reward(prompt, response)
    r_concise = conciseness_reward(response)
    r_code = code_quality_reward(response)
    
    return 0.2 * r_format + 0.4 * r_complete + 0.1 * r_concise + 0.3 * r_code

def load_dataset(dataset_path: str) -> Dataset:
    """
    Reads a jsonl dataset and converts it to a HuggingFace Dataset.
    Expects format: {"prompt": "...", "response": "..."}
    """
    if not os.path.exists(dataset_path):
        raise FileNotFoundError(f"Dataset file not found: {dataset_path}")
        
    prompts = []
    responses = []
    
    with open(dataset_path, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                data = json.loads(line)
                if "prompt" not in data:
                    print(f"Warning: Missing 'prompt' in line {line_num}")
                    continue
                prompts.append(data["prompt"])
                # trl GRPOTrainer expects 'completions' format for rewards if using format:
                # But here we just structure it as prompt.
                # Actually GRPO expects prompts to be in a specific format depending on the trainer.
                # Often it's just a 'prompt' column.
            except json.JSONDecodeError:
                print(f"Warning: Invalid JSON in line {line_num}")
                
    return Dataset.from_dict({"prompt": prompts})

def main():
    parser = argparse.ArgumentParser(description="GRPO Trainer for Project Ornith")
    parser.add_argument("--dataset", type=str, required=True, help="Path to the JSONL dataset")
    parser.add_argument("--model", type=str, default="unsloth/gemma-2-9b-it", help="HuggingFace model ID")
    parser.add_argument("--epochs", type=int, default=2, help="Number of training epochs")
    args = parser.parse_args()
    
    print(f"Loading dataset from {args.dataset}")
    try:
        dataset = load_dataset(args.dataset)
    except FileNotFoundError as e:
        print(f"Error: {e}")
        return
        
    print(f"Initializing model {args.model}")
    
    device = "mps" if torch.backends.mps.is_available() else "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Using device: {device}")
    
    tokenizer = AutoTokenizer.from_pretrained(args.model)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
        
    model = AutoModelForCausalLM.from_pretrained(
        args.model,
        torch_dtype=torch.float32,
        device_map=device
    )
    
    peft_config = LoraConfig(
        r=16,
        lora_alpha=32,
        target_modules=["q_proj", "v_proj"],
        bias="none",
        task_type="CAUSAL_LM"
    )
    model = get_peft_model(model, peft_config)
    
    # trl GRPO configuration
    training_args = GRPOConfig(
        output_dir="/Users/adarrsh/workspace/models/grpo-checkpoints/",
        learning_rate=5e-6,
        num_train_epochs=args.epochs,
        per_device_train_batch_size=1,
        gradient_accumulation_steps=4,
        max_prompt_length=1024,
        max_completion_length=1024,
        num_generations=4,
        beta=0.1,
        logging_steps=10,
        report_to="none"
    )
    
    # Define reward functions for GRPO
    # GRPOTrainer typically expects reward functions to take (prompts, completions, **kwargs)
    # We will wrap our composite reward to handle batch format
    def batch_reward_fn(prompts, completions, **kwargs):
        rewards = []
        for p, c in zip(prompts, completions):
            # Extract content if necessary, assuming string
            p_text = p if isinstance(p, str) else str(p)
            c_text = c if isinstance(c, str) else str(c)
            rewards.append(composite_reward(p_text, c_text))
        return rewards
    
    trainer = GRPOTrainer(
        model=model,
        reward_funcs=[batch_reward_fn],
        args=training_args,
        train_dataset=dataset,
        processing_class=tokenizer,
    )
    
    print("Starting training...")
    trainer.train()
    
    output_dir = "/Users/adarrsh/workspace/models/grpo-checkpoints/final"
    os.makedirs(output_dir, exist_ok=True)
    trainer.save_model(output_dir)
    print(f"Training complete. Model saved to {output_dir}")

if __name__ == "__main__":
    main()
