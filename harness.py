import json
import subprocess
import time
from pathlib import Path
import os

class ExecutionHarness:
    """
    A proprietary execution harness for running commands and recording trajectories
    in a format optimized for SkillOpt's self-evolution engine.
    """
    def __init__(self, task_id: str, workspace_dir: str):
        self.task_id = task_id
        self.workspace_dir = Path(workspace_dir)
        self.trajectories_dir = self.workspace_dir / ".tasks" / "trajectories"
        self.trajectories_dir.mkdir(parents=True, exist_ok=True)
        self.trajectory_file = self.trajectories_dir / f"{task_id}.jsonl"
        
        # Initialize file if not exists
        if not self.trajectory_file.exists():
            self._log_event({"type": "session_start", "task_id": task_id, "timestamp": time.time()})

    def _log_event(self, data: dict):
        """Appends a structured event to the trajectory file."""
        with self.trajectory_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(data) + "\n")

    def execute_command(self, command: str) -> str:
        """
        Executes a shell command, captures output, and logs the execution trace.
        
        Args:
            command: The shell command to run.
        Returns:
            The combined stdout/stderr of the command.
        """
        print(f"[Harness] Executing: {command}")
        start_time = time.time()
        
        try:
            res = subprocess.run(
                command, 
                shell=True, 
                capture_output=True, 
                text=True,
                cwd=str(self.workspace_dir)
            )
            
            end_time = time.time()
            output = res.stdout if res.returncode == 0 else res.stderr
            if not output.strip():
                output = f"[Exit code {res.returncode} - No output]"
            
            # Record trajectory
            self._log_event({
                "type": "command_execution",
                "command": command,
                "exit_code": res.returncode,
                "stdout": res.stdout,
                "stderr": res.stderr,
                "duration_sec": round(end_time - start_time, 2),
                "timestamp": end_time
            })
            
            return output

        except Exception as e:
            end_time = time.time()
            error_msg = f"Failed to execute command: {e}"
            
            self._log_event({
                "type": "command_error",
                "command": command,
                "error": str(e),
                "duration_sec": round(end_time - start_time, 2),
                "timestamp": end_time
            })
            
            return error_msg

    def execute_with_self_heal(self, command: str, max_retries: int = 3) -> str:
        """
        Executes a command and logs a retry prompt if it fails.
        """
        current_command = command
        for attempt in range(max_retries + 1):
            output = self.execute_command(current_command)
            
            exit_code = 0
            stderr = ""
            try:
                with open(self.trajectory_file, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                    if lines:
                        last_event = json.loads(lines[-1])
                        exit_code = last_event.get("exit_code", 0)
                        stderr = last_event.get("stderr", "")
            except Exception:
                pass
                
            if exit_code == 0:
                return output
                
            if attempt < max_retries:
                retry_prompt = f"The command `{current_command}` failed with error:\n{stderr}\nPlease analyze the error and suggest a fixed command."
                self._log_event({
                    "type": "self_heal_retry",
                    "original_command": current_command,
                    "retry_prompt": retry_prompt,
                    "attempt": attempt + 1,
                    "timestamp": time.time()
                })
                # Note: In a complete implementation, an LLM would process the retry_prompt
                # and provide a new current_command here. Without an LLM, we exit the loop.
                break
                
        return output

    def log_agent_action(self, action_type: str, input_data: str, output_data: str, reward: float = 0.0):
        """
        Logs arbitrary agent actions to the trajectory.
        """
        self._log_event({
            "type": "agent_action",
            "action_type": action_type,
            "input_data": input_data,
            "output_data": output_data,
            "reward": reward,
            "timestamp": time.time()
        })
