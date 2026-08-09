#!/usr/bin/env python3
import sys
import argparse
import time

try:
    from mlx_lm import load, generate
except ImportError:
    print("ERROR: mlx_lm is not installed in the current environment.", file=sys.stderr)
    sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="Ephemeral MLX Inference CLI")
    parser.add_argument("--model", type=str, required=True, help="HuggingFace Model ID or local path")
    parser.add_argument("--system", type=str, default="", help="System prompt")
    parser.add_argument("--prompt", type=str, required=True, help="User prompt")
    parser.add_argument("--max-tokens", type=int, default=1024, help="Max tokens to generate")
    parser.add_argument("--temp", type=float, default=0.2, help="Temperature")
    
    args = parser.parse_args()
    
    import logging
    logging.getLogger("transformers").setLevel(logging.ERROR)
    import transformers
    transformers.utils.logging.set_verbosity_error()

    try:
        model, tokenizer = load(args.model, tokenizer_config={"trust_remote_code": True})
    except Exception as e:
        print(f"ERROR: Failed to load model {args.model}: {e}", file=sys.stderr)
        sys.exit(1)
        
    messages = []
    if args.system:
        messages.append({"role": "system", "content": args.system})
    messages.append({"role": "user", "content": args.prompt})
    
    try:
        full_prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    except Exception as e:
        # Fallback if tokenizer lacks template
        full_prompt = f"{args.system}\n\n{args.prompt}" if args.system else args.prompt
        
    try:
        response = generate(
            model, 
            tokenizer, 
            prompt=full_prompt, 
            max_tokens=args.max_tokens,
            verbose=False
        )
        print(response.strip())
    except Exception as e:
        print(f"ERROR: Inference failed: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
