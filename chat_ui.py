import gradio as gr
from mlx_lm import load, generate

model_path = "/Users/adarrsh/workspace/models/fused-gemma"
print(f"Loading MLX model from {model_path}...")
model, tokenizer = load(model_path)
print("Model loaded successfully!")

def chat_with_mlx(message, history):
    messages = []
    for user_msg, bot_msg in history:
        messages.append({"role": "user", "content": user_msg})
        messages.append({"role": "model", "content": bot_msg})
    
    messages.append({"role": "user", "content": message})
    
    # Use the model's native chat template
    prompt = tokenizer.apply_chat_template(
        messages, 
        tokenize=False, 
        add_generation_prompt=True
    )
    
    # Generate response
    response = generate(
        model, 
        tokenizer, 
        prompt=prompt, 
        max_tokens=1024, 
        verbose=False
    )
    return response

demo = gr.ChatInterface(
    fn=chat_with_mlx,
    title="Ornith Gemma-2 9B (Local MLX)",
    description="Chat with your 100% offline, locally fine-tuned orchestrator running directly on your Mac GPU!",
)

if __name__ == "__main__":
    demo.launch(server_name="127.0.0.1", server_port=7860)
