import unittest
import tempfile
from pathlib import Path
from core.instruction_governance import ReporailsLinter, LocalFinding

class TestInstructionGovernance(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.ws = Path(self.tmp_dir.name)
        self.linter = ReporailsLinter()

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_lint_system_prompt_token_limit(self):
        # 3000 tokens of text
        huge_prompt = "instruction " * 12000
        findings = self.linter.lint_workspace(str(self.ws), huge_prompt)
        rule_ids = [f.rule_id for f in findings]
        self.assertIn("mechanical/token_limit", rule_ids)

    def test_lint_goal_vibe_words(self):
        goal = "Write a clean and robust microservice that has good performance."
        findings = self.linter.lint_goal(goal)
        rule_ids = [f.rule_id for f in findings]
        self.assertIn("deterministic/vibe_check", rule_ids)

    def test_lint_goal_security_destructive(self):
        goal = "Run rm -rf / to clear old builds and restart app.py"
        findings = self.linter.lint_goal(goal)
        rule_ids = [f.rule_id for f in findings]
        self.assertIn("security/destructive_rm", rule_ids)
        self.assertTrue(any(f.severity == "error" for f in findings))

    def test_lint_all_valid_workspace(self):
        valid_prompt = "You are a software engineer. Implement add(a, b) in math.py and run pytest."
        valid_goal = "Create math.py with add(a, b) and verify with pytest."
        findings, has_error = self.linter.lint_all(str(self.ws), valid_prompt, goal=valid_goal)
        self.assertFalse(has_error)

if __name__ == "__main__":
    unittest.main()
