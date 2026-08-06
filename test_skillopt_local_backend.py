import os
import sys

# Add skillopt repository to sys.path
sys.path.insert(0, "/Users/adarrsh/workspace/skillopt")

# Set environment variables BEFORE importing skillopt backend modules
os.environ["QWEN_CHAT_BASE_URL"] = "http://localhost:8800/v1"
os.environ["QWEN_CHAT_API_KEY"] = "dummy"
os.environ["QWEN_CHAT_MODEL"] = "AtomicChat/Ornith-9B-MLX-6bit"
os.environ["TARGET_DEPLOYMENT"] = "AtomicChat/Ornith-9B-MLX-6bit"
os.environ["OPTIMIZER_DEPLOYMENT"] = "AtomicChat/Ornith-9B-MLX-6bit"

from skillopt.model import set_backend, chat_target, qwen_backend

def main():
    print("Initializing SkillOpt local MLX GPU backend integration test...", flush=True)
    
    # Set backend to qwen_chat (OpenAI-compatible local server endpoint)
    set_backend("qwen_chat")
    
    # Force refresh Qwen config from environment
    qwen_backend.TARGET_CONFIG.base_url = "http://localhost:8800/v1"
    qwen_backend.TARGET_CONFIG.deployment = "AtomicChat/Ornith-9B-MLX-6bit"
    qwen_backend.TARGET_CONFIG.api_key = "dummy"
    
    qwen_backend.OPTIMIZER_CONFIG.base_url = "http://localhost:8800/v1"
    qwen_backend.OPTIMIZER_CONFIG.deployment = "AtomicChat/Ornith-9B-MLX-6bit"
    qwen_backend.OPTIMIZER_CONFIG.api_key = "dummy"
    
    print(f"Target Config Base URL: {qwen_backend.TARGET_CONFIG.base_url}", flush=True)
    print(f"Target Config Deployment: {qwen_backend.TARGET_CONFIG.deployment}", flush=True)
    
    print("\nSending test prompt through SkillOpt's chat_target interface...", flush=True)
    system_prompt = "You are a self-evolving coding agent powered by SkillOpt."
    user_prompt = "Write a python function to compute the factorial of n."
    
    response_text, token_info = chat_target(
        system=system_prompt,
        user=user_prompt,
        max_completion_tokens=150
    )
    
    print("\n--- SkillOpt Response from Local MLX GPU Engine ---", flush=True)
    print(response_text, flush=True)
    print(f"\nToken Usage Info: {token_info}", flush=True)
    print("\n✅ SkillOpt Local MLX Backend Integration Test PASSED!", flush=True)

if __name__ == "__main__":
    main()
