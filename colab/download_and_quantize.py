# -*- coding: utf-8 -*-
"""
Colab: Download & Quantize HuggingFace Model → GGUF → Google Drive
====================================================================
Open this in Colab: https://colab.research.google.com

This notebook:
  1. Downloads any HuggingFace model (works with free T4 GPU)
  2. Quantizes it to GGUF format using llama.cpp
  3. Saves to Google Drive for local sync

After running this, sync to your Mac:
  ~/workspace/scripts/sync_from_drive.sh
  ~/workspace/scripts/create_ollama_model.sh <model-name> <gguf-file>
"""

# ============================================================================
# Cell 1: Mount Google Drive
# ============================================================================
from google.colab import drive
drive.mount('/content/drive')

import os
MODEL_DIR = "/content/drive/MyDrive/ollama-models"
os.makedirs(MODEL_DIR, exist_ok=True)
print(f"✅ Models will be saved to: {MODEL_DIR}")

# ============================================================================
# Cell 2: Install dependencies
# ============================================================================
# !pip install -q huggingface_hub transformers torch
# !apt-get -qq install -y cmake build-essential
# !git clone --depth 1 https://github.com/ggerganov/llama.cpp /content/llama.cpp
# !cd /content/llama.cpp && cmake -B build && cmake --build build --config Release -j$(nproc)

# ============================================================================
# Cell 3: Configure — CHANGE THESE
# ============================================================================
# ── MODEL SETTINGS ──────────────────────────────────────────────────────────
HF_MODEL_ID    = "microsoft/Phi-3-mini-4k-instruct"  # ← CHANGE THIS
QUANT_METHOD   = "q4_k_m"                             # q4_k_m, q8_0, q5_k_m, f16
OUTPUT_NAME    = "phi3-mini"                           # ← friendly name for Ollama
# ─────────────────────────────────────────────────────────────────────────────

print(f"📦 Model:    {HF_MODEL_ID}")
print(f"📐 Quant:    {QUANT_METHOD}")
print(f"📝 Output:   {OUTPUT_NAME}-{QUANT_METHOD}.gguf")

# ============================================================================
# Cell 4: Download model from HuggingFace
# ============================================================================
from huggingface_hub import snapshot_download

local_model_path = f"/content/models/{OUTPUT_NAME}"
snapshot_download(
    repo_id=HF_MODEL_ID,
    local_dir=local_model_path,
    local_dir_use_symlinks=False,
)
print(f"✅ Downloaded to {local_model_path}")

# ============================================================================
# Cell 5: Convert to GGUF (FP16 base)
# ============================================================================
import subprocess

fp16_gguf = f"/content/{OUTPUT_NAME}-f16.gguf"
cmd_convert = [
    "python", "/content/llama.cpp/convert_hf_to_gguf.py",
    local_model_path,
    "--outfile", fp16_gguf,
    "--outtype", "f16",
]
print(f"🔄 Converting to FP16 GGUF...")
subprocess.run(cmd_convert, check=True)
print(f"✅ FP16 GGUF: {fp16_gguf}")

# ============================================================================
# Cell 6: Quantize to target precision
# ============================================================================
quantized_gguf = f"/content/{OUTPUT_NAME}-{QUANT_METHOD}.gguf"
cmd_quantize = [
    "/content/llama.cpp/build/bin/llama-quantize",
    fp16_gguf,
    quantized_gguf,
    QUANT_METHOD.upper(),
]
print(f"🔄 Quantizing to {QUANT_METHOD}...")
subprocess.run(cmd_quantize, check=True)

# Show file size
size_gb = os.path.getsize(quantized_gguf) / (1024 ** 3)
print(f"✅ Quantized: {quantized_gguf} ({size_gb:.2f} GB)")

# ============================================================================
# Cell 7: Copy to Google Drive
# ============================================================================
import shutil

drive_dest = os.path.join(MODEL_DIR, f"{OUTPUT_NAME}-{QUANT_METHOD}.gguf")
shutil.copy2(quantized_gguf, drive_dest)
print(f"✅ Saved to Google Drive: {drive_dest}")
print(f"")
print(f"Next steps on your Mac:")
print(f"  1. Run: ~/workspace/scripts/sync_from_drive.sh")
print(f"  2. Run: ~/workspace/scripts/create_ollama_model.sh {OUTPUT_NAME} {OUTPUT_NAME}-{QUANT_METHOD}.gguf")
print(f"  3. Test: ollama run {OUTPUT_NAME}")

# ============================================================================
# Cell 8: Optional — Push to HuggingFace Hub (for sharing)
# ============================================================================
# from huggingface_hub import HfApi
# api = HfApi()
# api.upload_file(
#     path_or_fileobj=quantized_gguf,
#     path_in_repo=f"{OUTPUT_NAME}-{QUANT_METHOD}.gguf",
#     repo_id="YOUR_USERNAME/YOUR_REPO",  # ← create this first
#     repo_type="model",
# )
# print("✅ Pushed to HuggingFace Hub")
