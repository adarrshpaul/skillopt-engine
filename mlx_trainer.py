import json
import os
import subprocess
from pathlib import Path

# Setup directories
WORKSPACE = Path("/Users/adarrsh/workspace")
DATA_DIR = WORKSPACE / "data"
DATA_DIR.mkdir(exist_ok=True)

# 1. Format Dataset for MLX and Gemma 2
# Gemma 2 chat template: <start_of_turn>role\n...<end_of_turn>
print("Formatting dataset for MLX Gemma 2...")
input_file = WORKSPACE / "dataset.jsonl"
train_file = DATA_DIR / "train.jsonl"
valid_file = DATA_DIR / "valid.jsonl"

formatted_data = []
if input_file.exists():
    with open(input_file, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            data = json.loads(line)
            prompt = data.get("prompt", "").strip()
            response = data.get("response", "").strip()
            
            # Format according to Gemma 2 chat template
            text = f"<start_of_turn>user\n{prompt}<end_of_turn>\n<start_of_turn>model\n{response}<end_of_turn>"
            formatted_data.append({"text": text})

if not formatted_data:
    print("No valid data found in dataset.jsonl. Exiting.")
    exit(1)

# Split 90% train, 10% valid (for very small datasets, just put all in train and copy to valid)
split_idx = max(1, int(len(formatted_data) * 0.9))
train_data = formatted_data[:split_idx]
valid_data = formatted_data[split_idx:] if split_idx < len(formatted_data) else formatted_data

# Write to disk
with open(train_file, "w", encoding="utf-8") as f:
    for item in train_data:
        f.write(json.dumps(item) + "\n")
        
with open(valid_file, "w", encoding="utf-8") as f:
    for item in valid_data:
        f.write(json.dumps(item) + "\n")

print(f"Dataset formatted! {len(train_data)} train samples, {len(valid_data)} valid samples.")

# 2. Run Apple MLX Fine-Tuning
# We use the 4-bit quantized base model to easily fit in 16GB Unified Memory
model_name = "mlx-community/gemma-2-9b-it-4bit"
adapter_path = WORKSPACE / "models" / "mlx-adapter"

print("\n🚀 Starting MLX LoRA Fine-Tuning on Apple Silicon...")
try:
    subprocess.run([
        "/Users/adarrsh/workspace/ml-env/bin/python", "-m", "mlx_lm.lora",
        "--model", model_name,
        "--train",
        "--data", str(DATA_DIR),
        "--iters", "200",               # Adjust iterations based on dataset size
        "--learning-rate", "1e-5",
        "--batch-size", "1",            # Keep batch size 1 for 16GB RAM
        "--grad-checkpoint",            # Crucial to prevent OOM
        "--adapter-path", str(adapter_path)
    ], check=True)
except subprocess.CalledProcessError as e:
    print(f"MLX Training failed with error: {e}")
    exit(1)

print(f"\n✅ Training complete! Adapter saved to {adapter_path}")

# 3. Export to Ollama compatible GGUF format
print("\n📦 Exporting to Ollama format...")
try:
    subprocess.run([
        "/Users/adarrsh/workspace/ml-env/bin/python", "-m", "mlx_lm.fuse",
        "--model", model_name,
        "--adapter-path", str(adapter_path),
        "--save-path", str(WORKSPACE / "models" / "fused-gemma")
    ], check=True)
    
    print("Model fused successfully. To load into Ollama, you can point a Modelfile FROM the fused directory.")
except subprocess.CalledProcessError as e:
    print(f"Fusing failed: {e}")
