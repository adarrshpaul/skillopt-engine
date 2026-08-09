"""SWE-bench QA Harness Integration."""
import sys
import os
import pytest

# Add workspace to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from orchestrator import run_task_graph
import autoqa.sandbox as sandbox
import time

# We will support a list of YAML test definitions here via parametrization
TEST_CASES = [
    {
        "instance_id": "django__django-11422",
        "problem_statement": "Add a tracking flag to autoreload to track changes in manage.py. This should automatically restart the server when manage.py is edited.",
        "repo": "django/django",
        "test_cmd": "python tests/runtests.py --settings=test_sqlite autoreload",
        "expected_output": "PASSED"
    }
]

@pytest.mark.backend
@pytest.mark.parametrize("task", TEST_CASES, ids=lambda x: x["instance_id"])
def test_swe_bench(task):
    """Run a single SWE-bench task through the SkillOpt orchestrator."""
    print(f"\n📦 Loaded SWE-Bench Task: {task['instance_id']}")
    print(f"📝 Problem Statement: {task['problem_statement']}")
    
    try:
        # 1. Native Venv Execution
        # (Sandbox will create a venv directly instead of pulling a docker image)
        
        # 2. Run Orchestrator to generate patch
        # Note: We simulate patch generation for the sandbox loop
        # run_task_graph will dump completion_report.md or similar, but for true sandboxing
        # we would capture the patch from git diff inside the workspace.
        # For now, let's just assert the sandbox functions correctly.
        start = time.time()
        run_task_graph(task["problem_statement"])
        
        # 3. Apply Patch to Sandbox
        # (Assuming orchestrator produces a patch file, for now we pass a dummy)
        res = sandbox.run_patch_tests(task["repo"], task["instance_id"], "DUMMY PATCH", task.get("test_cmd", "pytest"))
        
        if res != "PASSED":
            pytest.fail(f"Sandbox Verification Failed: {res}")
            
    except Exception as e:
        pytest.fail(f"Benchmark Run Failed: {e}")
