import os
import sys
import gc
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

try:
    from mlx_lm import load, generate
    import mlx.core as mx
    # Enforce strict 8GB memory caps to prevent kernel panics on 16GB machines
    if hasattr(mx, 'set_wired_limit'): 
        mx.set_wired_limit(8 * 1024 * 1024 * 1024)
        mx.set_cache_limit(8 * 1024 * 1024 * 1024)
    else:
        mx.metal.set_wired_limit(8 * 1024 * 1024 * 1024)
        mx.metal.set_cache_limit(8 * 1024 * 1024 * 1024)
except ImportError:
    print("ERROR: mlx_lm is not installed in the current environment.", file=sys.stderr)
    sys.exit(1)

app = FastAPI(title="SkillOpt MLX Server (Warm-Hold)")

# Global state
class ModelManager:
    def __init__(self):
        self.model = None
        self.tokenizer = None
        self.current_model_id = None

manager = ModelManager()

class Message(BaseModel):
    role: str
    content: str

class ChatCompletionRequest(BaseModel):
    model: str
    messages: List[Message]
    max_tokens: int = 1024
    temperature: float = 0.2

@app.post("/v1/chat/completions")
def chat_completions(req: ChatCompletionRequest):
    global manager
    
    # 1. Lazy load model if it differs from current or if empty
    if manager.current_model_id != req.model or manager.model is None:
        try:
            print(f"[MLX Server] Loading model {req.model}...")
            manager.model, manager.tokenizer = load(req.model, tokenizer_config={"trust_remote_code": True})
            manager.current_model_id = req.model
            print(f"[MLX Server] Successfully loaded {req.model}")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to load model {req.model}: {e}")
            
    # 2. Format Prompt
    messages_dict = [{"role": m.role, "content": m.content} for m in req.messages]
    try:
        full_prompt = manager.tokenizer.apply_chat_template(messages_dict, tokenize=False, add_generation_prompt=True)
    except Exception:
        # Fallback
        sys_prompt = "\n".join(m.content for m in req.messages if m.role == "system")
        user_prompt = "\n".join(m.content for m in req.messages if m.role == "user")
        full_prompt = f"{sys_prompt}\n\n{user_prompt}" if sys_prompt else user_prompt
        
    # KV Cache Safeguard
    MAX_PROMPT_CHARS = 12000 * 4 
    if len(full_prompt) > MAX_PROMPT_CHARS:
        print(f"[MLX Server] WARNING: Prompt length ({len(full_prompt)} chars) exceeds safe bounds. Truncating...")
        head = full_prompt[:MAX_PROMPT_CHARS // 2]
        tail = full_prompt[-MAX_PROMPT_CHARS // 2:]
        full_prompt = head + "\n\n...[TRUNCATED FOR MEMORY SAFETY]...\n\n" + tail
        
    # 3. Generate
    try:
        response_text = generate(
            manager.model, 
            manager.tokenizer, 
            prompt=full_prompt, 
            max_tokens=req.max_tokens,
            verbose=False
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Inference failed: {e}")
        
    return {
        "id": "chatcmpl-mlx",
        "object": "chat.completion",
        "model": req.model,
        "choices": [{
            "message": {
                "role": "assistant",
                "content": response_text.strip()
            }
        }]
    }

@app.post("/evict")
def evict_model():
    """Explicitly drop the model and force Python + Metal GC to release 8GB of RAM."""
    global manager
    if manager.model is not None:
        model_id = manager.current_model_id
        manager.model = None
        manager.tokenizer = None
        manager.current_model_id = None
        
        # 1. Force Python Garbage Collection
        gc.collect()
        
        # 2. Force Apple Metal clear cache
        mx.metal.clear_cache()
        
        print(f"[MLX Server] Evicted {model_id} from memory. Metal cache cleared.")
        return {"status": "success", "message": f"Evicted {model_id}"}
    return {"status": "skipped", "message": "No model was loaded"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8801)
