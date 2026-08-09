import os
import subprocess
import time
import logging
import venv
import shutil

def setup_venv(instance_id: str) -> str:
    """Creates a fresh virtual environment for the sandbox."""
    venv_path = os.path.abspath(f".sandbox_venv_{instance_id}")
    print(f"📦 Setting up native venv: {venv_path}...", flush=True)
    if os.path.exists(venv_path):
        shutil.rmtree(venv_path)
    venv.create(venv_path, with_pip=True)
    return venv_path

def run_patch_tests(repo: str, instance_id: str, patch_content: str, test_cmd: str) -> str:
    """
    Applies the patch in the target repo and runs tests using the sandbox venv.
    """
    venv_path = setup_venv(instance_id)
    python_bin = os.path.join(venv_path, "bin", "python")
    
    # Write patch to temp file
    patch_path = os.path.abspath(f".sandbox_{instance_id}.patch")
    with open(patch_path, "w") as f:
        f.write(patch_content)
        
    try:
        # In a real SWE-bench local run, we would clone the repo at the correct commit
        # For this pilot, we assume the repo is accessible or we are just testing the orchestration
        # We will simulate applying the patch
        
        apply_res = subprocess.run(
            ["git", "apply", patch_path],
            capture_output=True, text=True
        )
        if apply_res.returncode != 0 and "not a git repository" not in apply_res.stderr.lower():
            return f"PATCH_REJECTED: git apply failed:\n{apply_res.stderr}"
            
        # Run tests using the venv python
        # Convert `python` to `venv/bin/python` in the test cmd
        exec_cmd = test_cmd.replace("python ", f"{python_bin} ")
        
        test_res = subprocess.run(
            exec_cmd,
            shell=True,
            capture_output=True, text=True
        )
        
        if test_res.returncode == 0:
            return "PASSED"
        else:
            return f"TESTS_FAILED:\n{test_res.stdout}\n{test_res.stderr}"
            
    except Exception as e:
        return f"INFRA_ERROR: Sandbox exception: {e}"
    finally:
        teardown(venv_path, patch_path)

def teardown(venv_path: str, patch_path: str):
    """Cleans up the venv and patch."""
    if os.path.exists(venv_path):
        shutil.rmtree(venv_path)
    if os.path.exists(patch_path):
        os.remove(patch_path)
