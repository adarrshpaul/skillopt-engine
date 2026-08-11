import os
import sys
import time
import json
from pathlib import Path
from terminal_bench.agents.base_agent import BaseAgent, AgentResult
from terminal_bench.agents.failure_mode import FailureMode
from terminal_bench.terminal.tmux_session import TmuxSession
from terminal_bench.terminal.models import TerminalCommand
import litellm
from e2b import Sandbox

# Ensure nanobot is importable
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "nanobot")))

# Configure litellm to use local models
litellm.api_base = "http://localhost:8801/v1"
litellm.api_key = "sk-mock-key"

class NanobotAgent(BaseAgent):
    @staticmethod
    def name() -> str:
        return "nanobot_e2b_adapter"

    def perform_task(
        self,
        instruction: str,
        session: TmuxSession | None = None,
        logging_dir: Path | None = None,
    ) -> AgentResult:
        print(f"[NanobotAgent] Starting task: {instruction[:100]}...")
        
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "execute_bash",
                    "description": "Executes a bash command in the remote container and returns the terminal output.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "command": {
                                "type": "string",
                                "description": "The shell command to run (e.g. 'ls -la', 'npm test')"
                            }
                        },
                        "required": ["command"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "submit_task",
                    "description": "Submit the final answer or indicate completion of the task.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "reasoning": {
                                "type": "string",
                                "description": "Explanation of why the task is complete."
                            }
                        },
                        "required": ["reasoning"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "read_file",
                    "description": "Reads the contents of a file.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {
                                "type": "string",
                                "description": "The file path to read"
                            }
                        },
                        "required": ["path"]
                    }
                }
            }
        ]

        messages = [
            {"role": "system", "content": """You are a backend development expert running inside a Linux terminal via an interactive tmux session. You MUST output your actions as JSON tool calls.

Available tools:
1. execute_bash
Description: Executes a bash command in the remote container and returns the terminal output.
Arguments: {"command": "<shell command>"}

2. write_file
Description: Writes content to a file.
Arguments: {"path": "<file path>", "content": "<file content>"}

3. read_file
Description: Reads the contents of a file.
Arguments: {"path": "<file path>"}

4. submit_task
Description: Submit the final answer or indicate completion of the task.
Arguments: {"reasoning": "<explanation>"}

To use a tool, your entire output must be a single JSON object exactly like this:
{
    "name": "execute_bash",
    "arguments": {
        "command": "ls -la"
    }
}
Do NOT output any markdown, only the raw JSON object."""},
            {"role": "user", "content": f"Task Instruction:\n{instruction}"}
        ]

        total_in = 0
        total_out = 0
        failure = FailureMode.NONE

        try:
            if not session:
                print("[NanobotAgent] Spinning up E2B Sandbox for task...")
                from contextlib import contextmanager
                
                @contextmanager
                def get_sandbox():
                    with Sandbox.create("base") as s:
                        yield s
            else:
                print("[NanobotAgent] Using provided TmuxSession...")
                from contextlib import contextmanager
                
                @contextmanager
                def get_sandbox():
                    yield None
            
            with get_sandbox() as e2b_sandbox:
                for step in range(15):  # Max 15 steps
                    print(f"[NanobotAgent] Step {step+1}: Thinking...")
                    response = litellm.completion(
                        model="openai/mlx-community/Ling-mini-2.0-4bit",
                        messages=messages,
                        api_base="http://localhost:8801/v1",
                        api_key="sk-mock-key",
                        temperature=0.1,
                        max_tokens=2048
                    )
                    
                    msg = response.choices[0].message
                    messages.append({"role": "assistant", "content": msg.content})
                    
                    if hasattr(response, 'usage') and response.usage:
                        total_in += response.usage.prompt_tokens
                        total_out += response.usage.completion_tokens

                    content = msg.content or ""
                    try:
                        import re
                        json_str = content.strip()
                        # Extract json block if wrapped in markdown
                        match = re.search(r'```(?:json)?\n(.*?)\n```', content, re.DOTALL)
                        if match:
                            json_str = match.group(1).strip()
                        
                        # Extract just the first complete JSON object in case it concatenated multiple
                        import json
                        decoder = json.JSONDecoder()
                        # find the first '{'
                        start_idx = json_str.find('{')
                        if start_idx != -1:
                            parsed_obj, _ = decoder.raw_decode(json_str[start_idx:])
                        else:
                            raise ValueError("No '{' found in output.")
                            
                        tool_name = parsed_obj.get("name")
                        args = parsed_obj.get("arguments", {})
                    except Exception as e:
                        print(f"[NanobotAgent] Failed to parse tool call. Content:\n{content}\n---")
                        messages.append({"role": "user", "content": "Error: You must output a valid JSON tool call. Do not write text."})
                        continue

                    import uuid
                    fake_id = "call_" + str(uuid.uuid4())[:8]

                    if tool_name == "submit_task":
                        print(f"[NanobotAgent] Task submitted: {args.get('reasoning')}")
                        break
                    elif tool_name == "execute_bash":
                        cmd = args.get("command", "")
                        print(f"[NanobotAgent] Executing: {cmd}")
                        
                        if session:
                            session.send_command(TerminalCommand(command=cmd, block=True, max_timeout_sec=30.0))
                            output = session.get_incremental_output()
                        else:
                            process = e2b_sandbox.commands.run(cmd)
                            output = process.stdout + "\n" + process.stderr
                        
                        print(f"[NanobotAgent] Output (len={len(output)})")
                        messages.append({
                            "role": "user",
                            "content": f"Command output:\n{output[-2000:]}"
                        })
                    elif tool_name == "write_file":
                        path = args.get("path", "")
                        file_content = args.get("content", "")
                        print(f"[NanobotAgent] Writing to: {path}")
                        try:
                            if session:
                                # Escape the content for bash echo
                                escaped_content = file_content.replace("'", "'\\''")
                                cmd = f"cat << 'EOF' > {path}\n{file_content}\nEOF"
                                session.send_command(TerminalCommand(command=cmd, block=True, max_timeout_sec=30.0))
                                output = session.get_incremental_output()
                                messages.append({
                                    "role": "user",
                                    "content": f"Successfully wrote to {path}\nOutput:\n{output[-500:]}"
                                })
                            else:
                                # e2b API for writing file
                                e2b_sandbox.files.write(path, file_content)
                                messages.append({
                                    "role": "user",
                                    "content": f"Successfully wrote to {path}"
                                })
                        except Exception as e:
                            messages.append({
                                "role": "user",
                                "content": f"Error writing file: {e}"
                            })
                    elif tool_name == "read_file":
                        path = args.get("path", "")
                        print(f"[NanobotAgent] Reading from: {path}")
                        try:
                            if session:
                                cmd = f"cat {path}"
                                session.send_command(TerminalCommand(command=cmd, block=True, max_timeout_sec=30.0))
                                output = session.get_incremental_output()
                                messages.append({
                                    "role": "user",
                                    "content": f"File content of {path}:\n{output}"
                                })
                            else:
                                output = e2b_sandbox.files.read(path)
                                messages.append({
                                    "role": "user",
                                    "content": f"File content of {path}:\n{output}"
                                })
                        except Exception as e:
                            messages.append({
                                "role": "user",
                                "content": f"Error reading file: {e}"
                            })
                    else:
                        messages.append({"role": "user", "content": f"Error: Tool {tool_name} not found."})

        except Exception as e:
            print(f"[NanobotAgent] Exception during ReAct loop: {e}")
            failure = FailureMode.UNKNOWN_AGENT_ERROR

        print(f"\n[NanobotAgent] Task completed.")
        try:
            if not session and 'e2b_sandbox' in locals():
                print(f"Web server is available at: 👉 https://{e2b_sandbox.get_host(8000)} 👈")
                print("[NanobotAgent] Keeping sandbox alive for 120 seconds so you can view the app...")
                time.sleep(120)
        except Exception:
            pass

        return AgentResult(
            total_input_tokens=total_in,
            total_output_tokens=total_out,
            failure_mode=failure
        )

