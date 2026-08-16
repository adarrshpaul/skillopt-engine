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
import model_router
from core.session_ledger import JSONLSessionLedger, SessionEvent
from core.safety_gate import evaluate_tool_call, Decision
from core.tool_pipeline import parse_tool_calls_from_text, ToolCall
from contracts import GuardContext

# Ensure nanobot is importable
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "nanobot")))

# Configure litellm to use model_router
_planner_url = model_router.get_url("planner")
litellm.api_base = _planner_url
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
            },
            {
                "type": "function",
                "function": {
                    "name": "write_file",
                    "description": "Writes content to a file in the workspace.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {
                                "type": "string",
                                "description": "The file path to write"
                            },
                            "content": {
                                "type": "string",
                                "description": "The content to write"
                            }
                        },
                        "required": ["path", "content"]
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

        import uuid
        adapter_session_id = uuid.uuid4().hex[:8]
        ledger_path = Path("runs") / f"tb_session_{adapter_session_id}.jsonl"
        ledger = JSONLSessionLedger(ledger_path, session_id=adapter_session_id)
        ledger.append(SessionEvent(event_type="task/start", payload={"instruction": instruction[:500]}))

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
                    ledger.append(SessionEvent(event_type="step/start", payload={"step": step + 1}))

                    response = litellm.completion(
                        model=f"openai/{model_router.get_model('planner')}",
                        messages=messages,
                        api_base=model_router.get_url('planner'),
                        api_key="sk-mock-key",
                        temperature=0.1,
                        max_tokens=2048
                    )
                    
                    msg = response.choices[0].message
                    messages.append({"role": "assistant", "content": msg.content})
                    
                    step_in = 0
                    step_out = 0
                    if hasattr(response, 'usage') and response.usage:
                        step_in = response.usage.prompt_tokens
                        step_out = response.usage.completion_tokens
                        total_in += step_in
                        total_out += step_out

                    ledger.append(SessionEvent(
                        event_type="assistant/message",
                        tokens_in=step_in,
                        tokens_out=step_out,
                        payload={"content": (msg.content or "")[:500]}
                    ))

                    content = msg.content or ""
                    parsed_calls = parse_tool_calls_from_text(content)
                    if parsed_calls:
                        tool_name = parsed_calls[0].name
                        args = parsed_calls[0].args
                    else:
                        try:
                            import re
                            json_str = content.strip()
                            match = re.search(r'```(?:json)?\n(.*?)\n```', content, re.DOTALL)
                            if match:
                                json_str = match.group(1).strip()
                            
                            import json
                            decoder = json.JSONDecoder()
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

                    # Pre-execution Safety Evaluation
                    guard_ctx = GuardContext(worktree_root=os.getcwd(), active_role="coder", session_id=session_id)
                    guard = evaluate_tool_call(tool_name, args, guard_ctx)
                    if guard.decision == "deny":
                        print(f"🛑 [NanobotAgent] Blocked dangerous action [{guard.rule_id}]: {guard.reason}")
                        ledger.append(SessionEvent(event_type="guard/denied", payload={"tool": tool_name, "rule": guard.rule_id, "reason": guard.reason}))
                        messages.append({
                            "role": "user",
                            "content": f"BLOCKED [{guard.rule_id}]: {guard.reason}. Please choose a safe alternative."
                        })
                        continue

                    ledger.append(SessionEvent(event_type="tool/call", payload={"tool": tool_name, "args": args}))

                    if tool_name == "submit_task":
                        print(f"[NanobotAgent] Task submitted: {args.get('reasoning')}")
                        ledger.append(SessionEvent(event_type="task/submit", payload={"reasoning": args.get('reasoning')}))
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
                        ledger.append(SessionEvent(event_type="tool/result", payload={"tool": tool_name, "output": output[:500]}))
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
                                cmd = f"cat << 'EOF' > {path}\n{file_content}\nEOF"
                                session.send_command(TerminalCommand(command=cmd, block=True, max_timeout_sec=30.0))
                                output = session.get_incremental_output()
                                ledger.append(SessionEvent(event_type="tool/result", payload={"tool": tool_name, "path": path}))
                                messages.append({
                                    "role": "user",
                                    "content": f"Successfully wrote to {path}\nOutput:\n{output[-500:]}"
                                })
                            else:
                                e2b_sandbox.files.write(path, file_content)
                                ledger.append(SessionEvent(event_type="tool/result", payload={"tool": tool_name, "path": path}))
                                messages.append({
                                    "role": "user",
                                    "content": f"Successfully wrote to {path}"
                                })
                        except Exception as e:
                            ledger.append(SessionEvent(event_type="tool/error", payload={"tool": tool_name, "error": str(e)}))
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
                if os.environ.get("KEEP_ALIVE", "0") == "1":
                    print("[NanobotAgent] Keeping sandbox alive for 120 seconds so you can view the app...")
                    time.sleep(120)
        except Exception:
            pass

        return AgentResult(
            total_input_tokens=total_in,
            total_output_tokens=total_out,
            failure_mode=failure
        )

