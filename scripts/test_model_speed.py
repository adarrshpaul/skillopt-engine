import time
import os
import psutil
from mlx_lm import load, generate

def test_model(model_name: str, prompt: str = "Write a quick Python hello world script."):
    print(f"\n{'='*50}\nTesting Model: {model_name}\n{'='*50}")
    
    # Measure memory before loading
    process = psutil.Process(os.getpid())
    mem_before = process.memory_info().rss / (1024 ** 3)
    
    start_load = time.time()
    try:
        model, tokenizer = load(model_name)
    except Exception as e:
        print(f"Failed to load {model_name}: {e}")
        return
        
    load_time = time.time() - start_load
    mem_after = process.memory_info().rss / (1024 ** 3)
    ram_used = mem_after - mem_before
    
    print(f"✅ Loaded in {load_time:.2f}s | App RAM Usage: {mem_after:.2f} GB (Delta: +{ram_used:.2f} GB)")
    
    print("Generating tokens...")
    start_gen = time.time()
    
    # Generate ~100 tokens
    response = generate(model, tokenizer, prompt=prompt, max_tokens=100, verbose=False)
    
    gen_time = time.time() - start_gen
    
    # Count tokens (rough estimate via split for now, or tokenizer length)
    tokens = len(tokenizer.encode(response))
    tps = tokens / gen_time if gen_time > 0 else 0
    
    print(f"\nResponse (truncated): {response[:100]}...\n")
    print(f"📊 Speed: {tps:.2f} tokens/sec ({tokens} tokens in {gen_time:.2f}s)")
    
    # Cleanup memory
    del model
    del tokenizer
    print(f"Done testing {model_name}.")

if __name__ == "__main__":
    test_model("mlx-community/Ling-mini-2.0-4bit")
    test_model("AtomicChat/Ornith-9B-MLX-6bit")
