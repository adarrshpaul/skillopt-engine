import sys
import time
from playwright.sync_api import sync_playwright

def run_colab(notebook_url: str):
    print(f"🚀 Colab Orchestrator connecting to Chrome CDP at localhost:9222...")
    with sync_playwright() as p:
        try:
            # Attach to the running user Chrome instance (bypasses all bot-detection/2FA)
            browser = p.chromium.connect_over_cdp("http://localhost:9222")
            default_context = browser.contexts[0]
            page = default_context.new_page()
            
            print(f"🌐 Navigating to {notebook_url}")
            page.goto(notebook_url, timeout=60000)
            
            # Wait for Colab UI to fully load (the runtime connect button is a good indicator)
            print("⏳ Waiting for Colab UI to initialize...")
            page.wait_for_selector('colab-connect-button', timeout=60000)
            
            # Press Command+F9 (Mac) to "Run All"
            print("▶️ Executing 'Run All' command (Cmd+F9)")
            page.keyboard.press("Meta+F9")
            
            # Monitor for the completion output
            # We specifically look for the output text from our Jupyter Notebook
            print("📡 Monitoring execution logs...")
            success_selector = 'text="Done! Download lora.gguf and load it into your local Ollama Modelfile."'
            
            # This can take 15-30 minutes for training, so we use a huge timeout
            page.wait_for_selector(success_selector, timeout=3600000)  # 1 hour timeout
            
            print("✅ Training complete detected in DOM!")
            
            # Trigger download of lora.gguf
            # In Colab, we can execute JS in the console to trigger a file download via google.colab.files
            print("📥 Triggering GGUF download...")
            page.evaluate('''() => {
                const script = document.createElement("script");
                script.textContent = "google.colab.files.download('lora.gguf')";
                document.body.appendChild(script);
            }''')
            
            print("🎉 Colab Orchestration Successful! The file is downloading to your Chrome Downloads folder.")
            
            page.close()
            browser.close()
            
        except Exception as e:
            print(f"❌ Colab Orchestration failed: {e}")
            sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python colab_orchestrator.py <colab_notebook_url>")
        sys.exit(1)
        
    url = sys.argv[1]
    run_colab(url)
