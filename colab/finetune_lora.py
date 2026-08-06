# -*- coding: utf-8 -*-
"""
Colab: LoRA Fine-Tune → Merge → GGUF → Google Drive
=====================================================
Open this in Colab: https://colab.research.google.com
⚠️  Requires: GPU runtime (T4 free tier is sufficient)

This notebook:
  1. Fine-tunes a base model with LoRA using Unsloth (4x faster)
  2. Merges LoRA adapter back into the base model
  3. Exports to GGUF format
  4. Saves to Google Drive for local Ollama deployment

Use cases:
  - Fine-tune on Siemens iX component usage patterns
  - Fine-tune on IMS learning content
  - Fine-tune on your own coding style
"""

# ============================================================================
# Cell 1: Mount Google Drive
# ============================================================================
from google.colab import drive
drive.mount('/content/drive')

import os
MODEL_DIR = "/content/drive/MyDrive/ollama-models"
os.makedirs(MODEL_DIR, exist_ok=True)

# ============================================================================
# Cell 2: Install Unsloth (fastest LoRA on free Colab)
# ============================================================================
# !pip install -q "unsloth[colab-new] @ git+https://github.com/unslothai/unsloth.git"
# !pip install -q datasets trl

# ============================================================================
# Cell 3: Configure — CHANGE THESE
# ============================================================================
# ── MODEL ─────────────────────────────────────────────────────────────────────
BASE_MODEL     = "unsloth/Phi-3.5-mini-instruct"  # ← CHANGE THIS
OUTPUT_NAME    = "my-finetuned-model"              # ← CHANGE THIS
QUANT_METHOD   = "q4_k_m"                          # q4_k_m, q8_0, q5_k_m

# ── TRAINING ──────────────────────────────────────────────────────────────────
MAX_SEQ_LENGTH = 2048
LORA_RANK      = 16       # higher = more capacity, more VRAM
LORA_ALPHA     = 16
EPOCHS         = 3
BATCH_SIZE     = 2
LEARNING_RATE  = 2e-4
# ─────────────────────────────────────────────────────────────────────────────

print(f"📦 Base model:  {BASE_MODEL}")
print(f"📝 Output name: {OUTPUT_NAME}")
print(f"🎯 LoRA rank:   {LORA_RANK}")

# ============================================================================
# Cell 4: Load base model with Unsloth (4-bit for free tier)
# ============================================================================
from unsloth import FastLanguageModel

model, tokenizer = FastLanguageModel.from_pretrained(
    model_name=BASE_MODEL,
    max_seq_length=MAX_SEQ_LENGTH,
    dtype=None,            # auto-detect (float16 on T4)
    load_in_4bit=True,     # essential for free Colab T4
)

model = FastLanguageModel.get_peft_model(
    model,
    r=LORA_RANK,
    target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                     "gate_proj", "up_proj", "down_proj"],
    lora_alpha=LORA_ALPHA,
    lora_dropout=0,
    bias="none",
    use_gradient_checkpointing="unsloth",
    random_state=42,
)
print(f"✅ Model loaded. Trainable params: {model.print_trainable_parameters()}")

# ============================================================================
# Cell 5: Prepare your dataset
# ============================================================================
# OPTION A — Use a HuggingFace dataset:
from datasets import load_dataset

dataset = load_dataset("tatsu-lab/alpaca", split="train[:1000]")  # ← small sample

# OPTION B — Use your own JSONL file from Google Drive:
# dataset = load_dataset("json", data_files="/content/drive/MyDrive/my-data.jsonl", split="train")

# ── Format conversations ─────────────────────────────────────────────────────
PROMPT_TEMPLATE = """### Instruction:
{instruction}

### Input:
{input}

### Response:
{output}"""

def format_example(example):
    text = PROMPT_TEMPLATE.format(
        instruction=example.get("instruction", ""),
        input=example.get("input", ""),
        output=example.get("output", ""),
    )
    return {"text": text}

dataset = dataset.map(format_example)
print(f"✅ Dataset ready: {len(dataset)} examples")
print(f"   Sample: {dataset[0]['text'][:200]}...")

# ============================================================================
# Cell 6: Train with LoRA
# ============================================================================
from trl import SFTTrainer
from transformers import TrainingArguments

trainer = SFTTrainer(
    model=model,
    tokenizer=tokenizer,
    train_dataset=dataset,
    dataset_text_field="text",
    max_seq_length=MAX_SEQ_LENGTH,
    dataset_num_proc=2,
    packing=True,
    args=TrainingArguments(
        per_device_train_batch_size=BATCH_SIZE,
        gradient_accumulation_steps=4,
        warmup_steps=5,
        num_train_epochs=EPOCHS,
        learning_rate=LEARNING_RATE,
        fp16=True,
        logging_steps=10,
        optim="adamw_8bit",
        weight_decay=0.01,
        lr_scheduler_type="cosine",
        output_dir="/content/lora-output",
        report_to="none",
    ),
)

print("🔄 Training started...")
stats = trainer.train()
print(f"✅ Training complete!")
print(f"   Loss: {stats.training_loss:.4f}")
print(f"   Time: {stats.metrics['train_runtime']:.0f}s")

# ============================================================================
# Cell 7: Save LoRA adapter (checkpoint)
# ============================================================================
lora_dir = "/content/drive/MyDrive/ollama-models/lora-adapters/" + OUTPUT_NAME
model.save_pretrained(lora_dir)
tokenizer.save_pretrained(lora_dir)
print(f"✅ LoRA adapter saved to: {lora_dir}")

# ============================================================================
# Cell 8: Export merged model as GGUF
# ============================================================================
gguf_path = f"/content/{OUTPUT_NAME}-{QUANT_METHOD}.gguf"

model.save_pretrained_gguf(
    gguf_path.replace(f"-{QUANT_METHOD}.gguf", ""),
    tokenizer,
    quantization_method=QUANT_METHOD,
)

# Find the output file (Unsloth names it slightly differently)
import glob
gguf_files = glob.glob(f"/content/{OUTPUT_NAME}*.gguf")
if gguf_files:
    gguf_path = gguf_files[0]
    size_gb = os.path.getsize(gguf_path) / (1024 ** 3)
    print(f"✅ GGUF exported: {gguf_path} ({size_gb:.2f} GB)")
else:
    print("❌ GGUF export failed — check logs above")

# ============================================================================
# Cell 9: Copy GGUF to Google Drive
# ============================================================================
import shutil

drive_dest = os.path.join(MODEL_DIR, os.path.basename(gguf_path))
shutil.copy2(gguf_path, drive_dest)
print(f"✅ Saved to Google Drive: {drive_dest}")
print(f"")
print(f"Next steps on your Mac:")
print(f"  1. Run: ~/workspace/scripts/sync_from_drive.sh")
print(f"  2. Run: ~/workspace/scripts/create_ollama_model.sh {OUTPUT_NAME} {os.path.basename(gguf_path)}")
print(f"  3. Test: ollama run {OUTPUT_NAME}")

# ============================================================================
# Cell 10: Optional — Push GGUF to HuggingFace Hub
# ============================================================================
# from huggingface_hub import HfApi
# api = HfApi()
# api.upload_file(
#     path_or_fileobj=gguf_path,
#     path_in_repo=os.path.basename(gguf_path),
#     repo_id="YOUR_USERNAME/YOUR_REPO",
#     repo_type="model",
# )
