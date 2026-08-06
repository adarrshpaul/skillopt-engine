"""
Skill Compiler for the Steerable Skill Platform.

This module provides the compilation step for Project Ornith.
It takes a user-written markdown skill file describing an instruction or constraint,
and computes an Instruction Vector (IV) that encapsulates this skill.

Architecture:
1. We compute instruction vectors by running contrasting prompt pairs through a
   local HuggingFace Transformers model.
2. A pair consists of a "Positive" prompt (containing the constraint) and a
   "Negative" prompt (lacking the constraint).
3. We extract the hidden states of the last token at every layer for both sets.
4. The Instruction Vector for a specific layer is the mean difference between the
   positive and negative hidden states.
5. We identify the "best" layer by sweeping all layers and finding the one where
   the L2 norm of the difference vector is maximized.
6. The compiled vector is saved and can later be injected into the residual stream
   during inference to steer the model.
"""

import argparse
import logging
import os
import re
import sys
import math

try:
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
except ImportError:
    print("Error: torch and transformers are required. Please install them:")
    print("pip install torch transformers")
    sys.exit(1)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


def parse_skill(path: str) -> dict:
    """
    Parses a markdown skill file containing YAML-like frontmatter.
    Extracts name, constraint, and the body text.
    """
    if not os.path.exists(path):
        raise FileNotFoundError(f"Skill file not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    # Match frontmatter between --- and ---
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)", content, re.DOTALL)
    if not match:
        raise ValueError("Invalid skill format. Must start with --- YAML frontmatter ---")

    frontmatter = match.group(1)
    body = match.group(2).strip()

    name_match = re.search(r"^name:\s*(.+)$", frontmatter, re.MULTILINE)
    constraint_match = re.search(r"^constraint:\s*(.+)$", frontmatter, re.MULTILINE)

    if not name_match or not constraint_match:
        raise ValueError("Frontmatter must contain 'name' and 'constraint'")

    return {
        "name": name_match.group(1).strip(),
        "constraint": constraint_match.group(1).strip(),
        "body": body
    }


def generate_contrasting_pairs(constraint: str, n: int = 30) -> list[tuple[str, str]]:
    """
    Generates synthetic prompt pairs for vector computation using Contrastive Activation Addition (CAA).
    Positive: Includes the constraint.
    Negative: Omits the constraint.
    """
    base_questions = [
        "Write a Python script to sort a list.",
        "Explain how quantum computing works.",
        "Format this data as a table: apples, bananas, cherries.",
        "Find the bug in this code: print(1 + '1')",
        "Summarize the plot of Romeo and Juliet.",
        "Write a SQL query to select all users older than 30.",
        "Describe the process of photosynthesis.",
        "Create a simple HTML page with a button.",
        "Explain the difference between TCP and UDP.",
        "Give me a recipe for chocolate chip cookies.",
        "How do I reverse a string in JavaScript?",
        "What are the main causes of the French Revolution?",
        "Write a function to calculate the Fibonacci sequence.",
        "Compare and contrast REST and GraphQL.",
        "Tell me a short story about a brave knight."
    ]

    # Use up to n questions
    questions = base_questions[:n]
    if len(questions) < n:
        # Duplicate if n > 15
        questions = (questions * ((n // len(questions)) + 1))[:n]

    pairs = []
    for q in questions:
        positive = f"You must {constraint}. Now answer: {q}"
        negative = f"Answer: {q}"
        pairs.append((positive, negative))

    return pairs


def extract_hidden_states(model, tokenizer, text: str, device: str) -> dict[int, list[float]]:
    """
    Runs text through the model and extracts the hidden states of the LAST token at EVERY layer.
    """
    inputs = tokenizer(text, return_tensors="pt").to(device)
    
    with torch.no_grad():
        outputs = model(**inputs, output_hidden_states=True)
    
    hidden_states = outputs.hidden_states  # Tuple of (embedding_layer, layer_1, ..., layer_n)
    
    layer_states = {}
    for i, state in enumerate(hidden_states):
        # state shape: (batch_size, sequence_length, hidden_size)
        # Get the last token: state[0, -1, :]
        last_token_state = state[0, -1, :].cpu().tolist()
        layer_states[i] = last_token_state
        
    return layer_states


def compute_instruction_vector(positive_states: list, negative_states: list, layer: int) -> list[float]:
    """
    Computes IV as the mean difference for a specific layer.
    """
    # Each list contains dicts: {layer_idx: [hidden_dim]}
    pos_vectors = [s[layer] for s in positive_states]
    neg_vectors = [s[layer] for s in negative_states]

    num_samples = len(pos_vectors)
    hidden_dim = len(pos_vectors[0])

    iv = [0.0] * hidden_dim
    for i in range(hidden_dim):
        sum_pos = sum(pv[i] for pv in pos_vectors)
        sum_neg = sum(nv[i] for nv in neg_vectors)
        iv[i] = (sum_pos / num_samples) - (sum_neg / num_samples)

    return iv


def find_best_layer(positive_states: list, negative_states: list, num_layers: int, start_layer: int = 18, end_layer: int = 22) -> int:
    """
    Sweeps the specified middle layers (18-22), computes L2 norm of the difference vector, returns layer with highest norm.
    """
    best_layer = -1
    max_norm = -1.0

    # Target specific middle layers to preserve logic
    start = max(1, start_layer)
    end = min(num_layers, end_layer + 1)
    
    for layer in range(start, end):
        iv = compute_instruction_vector(positive_states, negative_states, layer)
        norm = math.sqrt(sum(val ** 2 for val in iv))
        if norm > max_norm:
            max_norm = norm
            best_layer = layer

    return best_layer


def compile_skill(skill_path: str, model_name: str, device: str):
    """
    Main orchestration function.
    """
    logging.info(f"Parsing skill from {skill_path}")
    skill = parse_skill(skill_path)
    skill_name = skill["name"]
    constraint = skill["constraint"]

    logging.info(f"Skill '{skill_name}' parsed. Constraint: {constraint}")
    
    pairs = generate_contrasting_pairs(constraint)
    logging.info(f"Generated {len(pairs)} contrasting prompt pairs.")

    logging.info(f"Loading model '{model_name}' on {device}...")
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModelForCausalLM.from_pretrained(model_name, torch_dtype=torch.float16 if device == "cuda" else torch.float32).to(device)
    model.eval()

    num_layers = model.config.num_hidden_layers + 1 # +1 for embedding

    positive_states = []
    negative_states = []

    logging.info("Extracting hidden states...")
    for pos_text, neg_text in pairs:
        positive_states.append(extract_hidden_states(model, tokenizer, pos_text, device))
        negative_states.append(extract_hidden_states(model, tokenizer, neg_text, device))

    logging.info("Finding best layer for injection...")
    best_layer = find_best_layer(positive_states, negative_states, num_layers)
    logging.info(f"Best layer identified: {best_layer}")

    logging.info("Computing Instruction Vector...")
    iv = compute_instruction_vector(positive_states, negative_states, best_layer)
    iv_tensor = torch.tensor(iv)

    out_dir = "/Users/adarrsh/workspace/skills/vectors"
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"{skill_name}.pt")

    save_dict = {
        "vector": iv_tensor,
        "layer": best_layer,
        "skill_name": skill_name,
        "constraint": constraint,
        "model": model_name
    }

    torch.save(save_dict, out_path)
    logging.info(f"Successfully compiled skill to {out_path}")
    
    return save_dict


def main():
    parser = argparse.ArgumentParser(description="Skill Compiler for Steerable Skill Platform")
    parser.add_argument("--skill", required=True, help="Path to the markdown skill file")
    parser.add_argument("--model", required=True, help="HuggingFace model name or path")
    parser.add_argument("--device", default="cpu", help="Device to run on (e.g. cpu, cuda, mps)")
    parser.add_argument("--dry-run", action="store_true", help="Parse file and generate pairs without loading model")
    
    args = parser.parse_args()

    if args.dry_run:
        logging.info("DRY RUN MODE ENABLED")
        skill = parse_skill(args.skill)
        logging.info(f"Parsed skill: {skill['name']}")
        logging.info(f"Constraint: {skill['constraint']}")
        pairs = generate_contrasting_pairs(skill['constraint'])
        logging.info(f"Generated {len(pairs)} pairs. First pair:")
        logging.info(f"  Positive: {pairs[0][0]}")
        logging.info(f"  Negative: {pairs[0][1]}")
        return

    compile_skill(args.skill, args.model, args.device)


if __name__ == "__main__":
    main()
