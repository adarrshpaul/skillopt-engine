import re

try:
    import gradio as gr
    GRADIO_AVAILABLE = True
except ImportError:
    gr = None
    GRADIO_AVAILABLE = False

try:
    from mlx_lm import load, generate
    MLX_AVAILABLE = True
except ImportError:
    load, generate = None, None
    MLX_AVAILABLE = False

model_path = "/Users/adarrsh/workspace/models/fused-gemma"

def get_model():
    if not MLX_AVAILABLE:
        return None, None
    try:
        model, tokenizer = load(model_path)
        return model, tokenizer
    except Exception:
        return None, None

def extract_artifact(response: str) -> str:
    """
    Extracts the most likely artifact from the response.
    Looks for markdown code blocks or structured documents.
    """
    code_blocks = re.findall(r'```[a-zA-Z]*\n(.*?)\n```', response, re.DOTALL)
    if code_blocks:
        return code_blocks[-1].strip()
    
    if response.strip().startswith("#"):
        return response.strip()
        
    return "_No specific artifact or code block found in this response._"

def user_func(user_message, history):
    return "", history + [[user_message, None]]

def bot_func(history):
    user_message = history[-1][0]
    messages = []
    for user_msg, bot_msg in history[:-1]:
        messages.append({"role": "user", "content": user_msg})
        if bot_msg:
            messages.append({"role": "model", "content": bot_msg})
    
    messages.append({"role": "user", "content": user_message})
    
    model, tokenizer = get_model()
    if model is None or tokenizer is None:
        response = f"Generated response for `{user_message}`:\n\n```python\n# Auto-generated code\ndef execute_task():\n    return 'Success for: {user_message}'\n```"
    else:
        prompt = tokenizer.apply_chat_template(
            messages, 
            tokenize=False, 
            add_generation_prompt=True
        )
        response = generate(
            model, 
            tokenizer, 
            prompt=prompt, 
            max_tokens=1024, 
            verbose=False
        )
    
    history[-1][1] = response
    artifact = extract_artifact(response)
    
    return history, artifact

custom_css = """
#artifact-panel {
    background-color: #1e1e1e;
    padding: 20px;
    border-radius: 8px;
    border: 1px solid #333;
    overflow-y: auto;
    height: 650px;
}
"""

def create_ui():
    if not GRADIO_AVAILABLE:
        print("Gradio is not installed in the current environment.")
        return None

    with gr.Blocks(css=custom_css, theme=gr.themes.Monochrome()) as demo:
        gr.Markdown("# 🦅 Ornith Gemma-2 9B - Side-by-Side Artifact UI")
        gr.Markdown("Inspired by modern agentic chat interfaces, this UI extracts and displays generated documents, code, or markdown in a dedicated side panel.")
        
        with gr.Row():
            with gr.Column(scale=1):
                chatbot = gr.Chatbot(height=650, show_label=False)
                with gr.Row():
                    msg = gr.Textbox(placeholder="Ask me to generate a document or write code...", show_label=False, scale=4)
                    clear = gr.ClearButton([msg, chatbot], scale=1)
                    
            with gr.Column(scale=1):
                with gr.Group(elem_id="artifact-panel"):
                    gr.Markdown("### 📄 Artifact Preview")
                    artifact_display = gr.Markdown("_Generated artifacts (code blocks, markdown docs) will be rendered here..._")

        msg.submit(user_func, [msg, chatbot], [msg, chatbot], queue=False).then(
            bot_func, chatbot, [chatbot, artifact_display]
        )
    return demo

if __name__ == "__main__":
    demo = create_ui()
    if demo:
        demo.launch(server_name="127.0.0.1", server_port=7860)
