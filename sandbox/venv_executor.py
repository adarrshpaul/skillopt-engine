import os
import subprocess
import shutil
import venv
import pty
import threading
import select
import re
import time
from abc import ABC, abstractmethod
from typing import Tuple

def strip_ansi(text: str) -> str:
    """Removes ANSI escape codes and terminal carriage returns."""
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return ansi_escape.sub('', text).replace('\r\n', '\n').replace('\r', '')

class SandboxEnvironment(ABC):
    """
    Abstract interface for executing code in an isolated environment.
    This enables seamless swapping between Native macOS venvs and Remote VPS execution.
    """
    
    @abstractmethod
    def setup(self, workspace_path: str) -> None:
        """Initialize the sandbox environment."""
        pass
        
    @abstractmethod
    def run_command(self, cmd: str, timeout: int = 60) -> Tuple[int, str, str]:
        """
        Execute a command within the sandbox.
        Returns (exit_code, stdout, stderr).
        """
        pass
        
    @abstractmethod
    def teardown(self) -> None:
        """Clean up the sandbox environment."""
        pass

class NativeVenvSandbox(SandboxEnvironment):
    """
    Executes commands within a native, isolated Python virtual environment on macOS.
    Zero persistent RAM tax compared to Docker Desktop.
    """
    
    def __init__(self):
        self.workspace_path = None
        self.venv_path = None
        self.background_tasks = {}
        self._next_task_id = 1
        
    def setup(self, workspace_path: str) -> None:
        self.workspace_path = os.path.abspath(workspace_path)
        self.venv_path = os.path.join(self.workspace_path, ".test_venv")
        
        # Create the venv
        print(f"[Sandbox] Creating native venv at {self.venv_path}...", flush=True)
        venv.create(self.venv_path, with_pip=True)
        
        # We can optionally install dependencies here if needed by the SWE-bench instance
        
    def run_command(self, cmd: str, timeout: int = 60) -> Tuple[int, str, str]:
        if not self.venv_path or not os.path.exists(self.venv_path):
            raise RuntimeError("Sandbox not initialized. Call setup() first.")
            
        # Wrap the command so it runs inside the venv context
        # On macOS/Linux, we source the activate script
        activate_script = os.path.join(self.venv_path, "bin", "activate")
        
        # Use bash -c to source the venv and then run the command
        wrapped_cmd = f"source {activate_script} && {cmd}"
        
        print(f"[Sandbox] Executing: {cmd}", flush=True)
        
        try:
            master, slave = pty.openpty()
            proc = subprocess.Popen(
                ["bash", "-c", wrapped_cmd],
                cwd=self.workspace_path,
                stdin=slave,
                stdout=slave,
                stderr=subprocess.STDOUT,
                start_new_session=True
            )
            os.close(slave)
            
            output_bytes = bytearray()
            start_time = time.time()
            
            while True:
                if proc.poll() is not None:
                    # Process exited, read remaining bytes
                    while True:
                        r, _, _ = select.select([master], [], [], 0.1)
                        if master in r:
                            try:
                                data = os.read(master, 1024)
                                if not data:
                                    break
                                output_bytes.extend(data)
                            except OSError:
                                break
                        else:
                            break
                    break
                    
                elapsed = time.time() - start_time
                if elapsed > timeout:
                    import signal
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                    os.close(master)
                    out_str = strip_ansi(output_bytes.decode('utf-8', errors='replace'))
                    return 124, out_str, f"TimeoutExpired: Command exceeded {timeout}s"
                    
                r, _, _ = select.select([master], [], [], 0.5)
                if master in r:
                    try:
                        data = os.read(master, 1024)
                        if not data:
                            break
                        output_bytes.extend(data)
                    except OSError:
                        break

            os.close(master)
            out_str = strip_ansi(output_bytes.decode('utf-8', errors='replace'))
            return proc.returncode, out_str, ""
                
        except Exception as e:
            return 1, "", str(e)
            
    def run_background_command(self, cmd: str) -> str:
        if not self.venv_path or not os.path.exists(self.venv_path):
            raise RuntimeError("Sandbox not initialized. Call setup() first.")
            
        activate_script = os.path.join(self.venv_path, "bin", "activate")
        wrapped_cmd = f"source {activate_script} && {cmd}"
        
        master, slave = pty.openpty()
        
        proc = subprocess.Popen(
            ["bash", "-c", wrapped_cmd],
            cwd=self.workspace_path,
            stdin=slave,
            stdout=slave,
            stderr=subprocess.STDOUT,
            start_new_session=True
        )
        os.close(slave)
        
        task_id = f"task_{self._next_task_id}"
        self._next_task_id += 1
        log_file = os.path.join(self.workspace_path, f".{task_id}.log")
        
        def pump_output(fd, log_path):
            with open(log_path, "wb") as f_out:
                while True:
                    try:
                        data = os.read(fd, 1024)
                        if not data:
                            break
                        f_out.write(data)
                        f_out.flush()
                    except OSError:
                        break
            os.close(fd)
            
        t = threading.Thread(target=pump_output, args=(master, log_file), daemon=True)
        t.start()
        
        self.background_tasks[task_id] = {
            "proc": proc,
            "cmd": cmd,
            "log_file": log_file,
            "thread": t
        }
        
        return task_id
        
    def manage_task(self, task_id: str, action: str) -> str:
        if task_id not in self.background_tasks:
            return f"ERROR: Task {task_id} not found."
            
        task = self.background_tasks[task_id]
        proc = task["proc"]
        
        if action == "status":
            retcode = proc.poll()
            status = "RUNNING" if retcode is None else f"EXITED({retcode})"
            try:
                with open(task["log_file"], "r") as f:
                    log_content = f.read()
                    if len(log_content) > 2000:
                        log_content = log_content[:1000] + "\\n...[TRUNCATED]...\\n" + log_content[-1000:]
            except Exception:
                log_content = "Could not read log."
            return f"Task {task_id} status: {status}\\nLog:\\n{log_content}"
            
        elif action == "kill":
            if proc.poll() is None:
                import signal
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                return f"Task {task_id} killed."
            return f"Task {task_id} already exited."
            
        return f"ERROR: Unknown action {action}."
            
    def teardown(self) -> None:
        for task_id, task in self.background_tasks.items():
            if task["proc"].poll() is None:
                import signal
                try:
                    os.killpg(os.getpgid(task["proc"].pid), signal.SIGKILL)
                except Exception:
                    pass
                
        if self.venv_path and os.path.exists(self.venv_path):
            print(f"[Sandbox] Tearing down native venv...", flush=True)
            shutil.rmtree(self.venv_path)
        self.workspace_path = None
        self.venv_path = None
