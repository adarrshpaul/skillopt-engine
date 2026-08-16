import unittest
import tempfile
from pathlib import Path
from core.tool_pipeline import ToolPipeline, ToolCall, ToolResult, parse_tool_calls_from_text
from core.session_ledger import JSONLSessionLedger

class TestToolPipeline(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp_dir.name)
        self.ledger = JSONLSessionLedger(self.tmp_path / "pipeline_session.jsonl")
        self.pipeline = ToolPipeline(ledger=self.ledger)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_tool_registration_and_execution(self):
        self.pipeline.register_tool("echo", lambda text: f"echoed: {text}")
        call = ToolCall(name="echo", args={"text": "hello world"})
        result = self.pipeline.dispatch(call)

        self.assertFalse(result.is_error)
        self.assertEqual(result.content, "echoed: hello world")

        # Verify events were logged to ledger
        events = self.ledger.replay(0)
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0].event_type, "tool/call")
        self.assertEqual(events[1].event_type, "tool/result")

    def test_safety_gate_pre_hook_blocks_malicious(self):
        self.pipeline.register_tool("bash", lambda command: "executed")
        call = ToolCall(name="bash", args={"command": "sudo rm -rf /"})
        result = self.pipeline.dispatch(call)

        self.assertTrue(result.is_error)
        self.assertIn("BLOCKED [R01:no-sudo]", result.content)

    def test_multi_grammar_parsing_execute_tags(self):
        text = 'I will run the test now.\n<execute>run_command("pytest tests/")</execute>'
        calls = parse_tool_calls_from_text(text)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0].name, "run_command")
        self.assertEqual(calls[0].args.get("command"), "pytest tests/")

    def test_multi_grammar_parsing_named_args(self):
        text = '<execute>write_file(path="app.py", content="print(\'hello\')")</execute>'
        calls = parse_tool_calls_from_text(text)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0].name, "write_file")
        self.assertEqual(calls[0].args.get("path"), "app.py")
        self.assertEqual(calls[0].args.get("content"), "print('hello')")

    def test_multi_grammar_parsing_positional_write_file(self):
        text = '<execute>write_file("app.py", "import flask\\napp = flask.Flask(__name__)\\n\\ndef get_status():\\n    return {\'status\': \'ok\'}\\n")</execute>'
        calls = parse_tool_calls_from_text(text)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0].name, "write_file")
        self.assertEqual(calls[0].args.get("path"), "app.py")
        self.assertIn("def get_status()", calls[0].args.get("content"))

if __name__ == "__main__":
    unittest.main()
