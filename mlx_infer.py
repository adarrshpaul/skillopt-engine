import sys
from mlx_lm import load, generate
import logging

logging.getLogger("mlx_lm").setLevel(logging.ERROR)

def main():
    model_path = "/Users/adarrsh/workspace/models/fused-gemma"
    prompt = sys.stdin.read()
    
    try:
        model, tokenizer = load(model_path)
        # Disable verbosity so we only print the model output
        response = generate(model, tokenizer, prompt=prompt, max_tokens=2048, verbose=False)
        print(response)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
