import os
import sys
import time

# Add workspace to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__))))

from custom_nanobot_adapter import NanobotAgent
from terminal_bench.terminal.tmux_session import TmuxSession

def main():
    print("=======================================")
    print("   NanobotAgent Web App E2B Demo       ")
    print("=======================================")
    print("Using local Ling-3.0 models via MLX Fleet.")
    
    agent = NanobotAgent()
    instruction = """
    Create a beautiful HTML/CSS/JS clock application. 
    1. Write the code to index.html using the write_file tool.
    2. Start a Python HTTP server on port 8000 in the background (using execute_bash with nohup ... &).
    3. Make sure to use modern design (glassmorphism, animations).
    4. When done, call submit_task.
    """
    
    print("\n[Demo] Triggering agent.perform_task()...")
    result = agent.perform_task(
        instruction=instruction,
        session=None
    )
    
    print("\n[Demo] Agent finished with result:")
    print(f"Total Input Tokens:  {result.total_input_tokens}")
    print(f"Total Output Tokens: {result.total_output_tokens}")
    print(f"Failure Mode:        {result.failure_mode.value}")

if __name__ == "__main__":
    main()
