import os
import subprocess
import shutil
import venv
from abc import ABC, abstractmethod
from typing import Tuple

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
            # We use start_new_session=True so we can kill the entire process group if it hangs
            proc = subprocess.Popen(
                ["bash", "-c", wrapped_cmd],
                cwd=self.workspace_path,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                start_new_session=True
            )
            
            try:
                stdout, stderr = proc.communicate(timeout=timeout)
                return proc.returncode, stdout, stderr
            except subprocess.TimeoutExpired:
                import signal
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                stdout, stderr = proc.communicate()
                return 124, stdout, f"TimeoutExpired: Command exceeded {timeout}s\n{stderr}"
                
        except Exception as e:
            return 1, "", str(e)
            
    def teardown(self) -> None:
        if self.venv_path and os.path.exists(self.venv_path):
            print(f"[Sandbox] Tearing down native venv...", flush=True)
            shutil.rmtree(self.venv_path)
        self.workspace_path = None
        self.venv_path = None
