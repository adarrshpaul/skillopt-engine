"""Fixture-driven admission controller tests.

Loads test cases from tests/fixtures/admission/*.json and validates
the AdmissionControllerServicer against each fixture's expected output.
This pattern is inspired by the Claude Code Harness fixture testing approach.
"""
import unittest
import json
import os
import sys
import glob

sys.path.insert(0, '/Users/adarrsh/workspace')

from admission_controller_grpc import AdmissionControllerServicer
from proto import admission_pb2


FIXTURES_DIR = os.path.join(os.path.dirname(__file__), 'fixtures', 'admission')


class TestAdmissionFixtures(unittest.TestCase):
    """Runs every JSON fixture in tests/fixtures/admission/ as a test case."""

    def setUp(self):
        self.controller = AdmissionControllerServicer()

    def _load_fixture(self, filename):
        path = os.path.join(FIXTURES_DIR, filename)
        with open(path) as f:
            return json.load(f)

    def _apply_setup(self, fixture):
        """Apply fixture setup overrides to the controller state."""
        setup = fixture.get('setup', {})
        if 'tokens' in setup:
            self.controller.p1_bucket.tokens = float(setup['tokens'])
        if 'preempt_budget' in setup:
            self.controller.preempt_budget = setup['preempt_budget']
        if 'queue_full' in setup and setup['queue_full']:
            # Fill the queue to capacity with dict items
            for i in range(self.controller.p2_queue.maxsize):
                try:
                    self.controller.p2_queue.put_nowait({"id": f"filler-{i}", "payload": "x"})
                except Exception:
                    break
        if 'p2_queue_has_task' in setup and setup['p2_queue_has_task']:
            self.controller.p2_queue.put_nowait({"id": "preemptable-task", "payload": "x"})
        if 'cpu_util' in setup:
            self.controller.composite_util = lambda: setup['cpu_util']
        if 'throttled' in setup and setup['throttled']:
            import time
            self.controller.p3_throttled_until = time.time() + 3600

    def _run_fixture(self, fixture):
        """Execute a single fixture against the admission controller."""
        self._apply_setup(fixture)

        inp = fixture['input']
        req = admission_pb2.AdmitRequest(
            id=inp.get('request_id', inp.get('id', 'test')),
            priority=inp['priority'],
            payload=inp.get('payload', '')
        )
        resp = self.controller.Admit(req, None)

        expected = fixture['expected']
        self.assertEqual(resp.action, expected['action'],
                         f"Expected action='{expected['action']}', got '{resp.action}' "
                         f"[fixture: {fixture.get('description', 'unknown')}]")

        if 'reason' in expected:
            self.assertEqual(resp.reason, expected['reason'])
        if 'has_checkpoint_token' in expected and expected['has_checkpoint_token']:
            self.assertTrue(len(resp.checkpoint_token) > 0,
                            "Expected a checkpoint_token but got empty string")

    def test_p1_grant(self):
        """P1 interactive request with available tokens."""
        self._run_fixture(self._load_fixture('p1_grant.json'))

    def test_p1_exhausted(self):
        """P1 request with zero tokens and zero preempt budget."""
        self._run_fixture(self._load_fixture('p1_exhausted.json'))

    def test_p2_queue(self):
        """P2 planner task queued successfully."""
        self._run_fixture(self._load_fixture('p2_queue.json'))

    def test_p2_full(self):
        """P2 queue at max capacity rejects."""
        self._run_fixture(self._load_fixture('p2_full.json'))

    def test_p1_preempt(self):
        """P1 preempts P2 when tokens exhausted but preempt budget available."""
        self._run_fixture(self._load_fixture('p1_preempt.json'))

    def test_p3_low_util(self):
        """P3 background job admitted under low CPU utilization."""
        self._run_fixture(self._load_fixture('p3_low_util.json'))

    def test_p3_high_util(self):
        """P3 background job throttled under high CPU utilization."""
        self._run_fixture(self._load_fixture('p3_high_util.json'))


class TestAPISchemaValidation(unittest.TestCase):
    """Validates live API responses against JSON schemas."""

    SCHEMAS_DIR = os.path.join(os.path.dirname(__file__), 'schemas')

    def _load_schema(self, name):
        path = os.path.join(self.SCHEMAS_DIR, name)
        with open(path) as f:
            return json.load(f)

    def _validate(self, data, schema):
        """Simple schema validation without jsonschema library."""
        # Check required fields
        for field in schema.get('required', []):
            self.assertIn(field, data, f"Missing required field: {field}")
        # Check field types
        props = schema.get('properties', {})
        for field, spec in props.items():
            if field in data:
                expected_type = spec.get('type')
                if expected_type == 'string':
                    self.assertIsInstance(data[field], str, f"{field} should be string")
                elif expected_type == 'integer':
                    self.assertIsInstance(data[field], int, f"{field} should be integer")
                elif expected_type == 'number':
                    self.assertIsInstance(data[field], (int, float), f"{field} should be number")
                elif expected_type == 'array':
                    self.assertIsInstance(data[field], list, f"{field} should be array")
                elif expected_type == 'object':
                    self.assertIsInstance(data[field], dict, f"{field} should be object")

    @unittest.skipUnless(
        os.system("curl -sf http://localhost:5002/api/fleet >/dev/null 2>&1") == 0,
        "Master Cockpit not running on :5002"
    )
    def test_fleet_schema(self):
        """Validate /api/fleet response matches schema."""
        import urllib.request
        resp = urllib.request.urlopen("http://localhost:5002/api/fleet", timeout=5)
        data = json.loads(resp.read())
        schema = self._load_schema('fleet_response.json')
        self._validate(data, schema)
        # Deep check: each role has required sub-fields
        for role_name, role_data in data.get('roles', {}).items():
            self.assertIn('model', role_data, f"Role {role_name} missing 'model'")
            self.assertIn('url', role_data, f"Role {role_name} missing 'url'")

    @unittest.skipUnless(
        os.system("curl -sf http://localhost:5002/api/telemetry >/dev/null 2>&1") == 0,
        "Master Cockpit not running on :5002"
    )
    def test_telemetry_schema(self):
        """Validate /api/telemetry response matches schema."""
        import urllib.request
        resp = urllib.request.urlopen("http://localhost:5002/api/telemetry", timeout=5)
        data = json.loads(resp.read())
        schema = self._load_schema('telemetry_response.json')
        self._validate(data, schema)


if __name__ == '__main__':
    unittest.main()
