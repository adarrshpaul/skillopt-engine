import json
import re
import ast

def parse_code_blocks(response, lang):
    """Extract code blocks from the markdown response."""
    pattern = rf"```(?:{lang})?\n(.*?)```"
    return re.findall(pattern, response, re.DOTALL)

def grade_response(response, expected_format):
    """
    Grades the response based on strict constraint adherence.
    Criteria:
    1. Must contain at least one code block.
    2. Must NOT contain conversational filler (e.g. 'Sure!', 'Here is the code', etc.)
    3. The code block must be valid (parsable python/bash).
    """
    # Check for code blocks
    blocks = parse_code_blocks(response, expected_format)
    if not blocks:
        return False, "No code blocks found"
    
    code = blocks[0]
    
    # Check for conversational filler (heuristic: text outside code blocks should be minimal or purely architectural)
    # For maximum strictness, we expect the output to basically just be the code block.
    text_without_blocks = re.sub(r"```.*?```", "", response, flags=re.DOTALL).strip()
    bad_fillers = ["sure", "here is", "certainly", "of course", "I can help", "Let's"]
    for filler in bad_fillers:
        if filler.lower() in text_without_blocks.lower():
            return False, f"Conversational filler detected: '{filler}'"
            
    # Check validity
    if expected_format == "python":
        try:
            ast.parse(code)
        except SyntaxError:
            return False, "Invalid Python syntax"
            
    return True, "Pass"

def run_evaluation():
    print("Loading benchmark tasks...")
    tasks = []
    with open("benchmark_tasks.jsonl", "r") as f:
        for line in f:
            tasks.append(json.loads(line))
            
    print(f"Loaded {len(tasks)} tasks.")
    
    methods = ["Prompting (Zero-Shot)", "Activation Steering", "LoRA Fine-Tuning"]
    results = {}
    
    print("\n--- Starting Evaluation Run ---\n")
    # In a real run, this would trigger the actual MLX inference engine
    # For now, this is the harness skeleton.
    print("Evaluator skeleton ready. Ready to hook into MLX inference.")

if __name__ == "__main__":
    run_evaluation()
