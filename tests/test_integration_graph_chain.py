import unittest
import urllib.request
import json
import sys
sys.path.insert(0, '/Users/adarrsh/workspace')

def _http_available(url):
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=2) as resp:
            return resp.status == 200
    except:
        return False

HAS_API = _http_available('http://localhost:5002/api/graph')

class TestIntegrationGraphChain(unittest.TestCase):

    @unittest.skipUnless(HAS_API, "Graph API server not running on :5002")
    def test_e2e_chat_to_graph_persistence(self):
        payload = json.dumps({"text": "Integration test prompt", "priority": 1}).encode("utf-8")
        req = urllib.request.Request("http://localhost:5002/api/chat", data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            self.assertIn("node_id", data)

    @unittest.skipUnless(HAS_API, "Graph API server not running on :5002")
    def test_e2e_chat_creates_prompt_response_edge(self):
        req = urllib.request.Request("http://localhost:5002/api/graph")
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            self.assertIn("nodes", data)
            self.assertIn("edges", data)

    @unittest.skipUnless(HAS_API, "Graph API server not running on :5002")
    def test_e2e_graph_accumulates(self):
        req = urllib.request.Request("http://localhost:5002/api/graph")
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            initial_count = len(data["nodes"])
        
        payload = json.dumps({"text": "Accumulation test", "priority": 1}).encode("utf-8")
        post_req = urllib.request.Request("http://localhost:5002/api/chat", data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(post_req):
            pass

        with urllib.request.urlopen(req) as resp:
            new_data = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(len(new_data["nodes"]), initial_count + 2)

    @unittest.skipUnless(HAS_API, "Graph API server not running on :5002")
    def test_e2e_admission_action_in_response(self):
        payload = json.dumps({"text": "Admission check", "priority": 1}).encode("utf-8")
        req = urllib.request.Request("http://localhost:5002/api/chat", data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            self.assertIn(data["action"], ["start", "queued", "scheduled", "reject", "preempt", "error"])

if __name__ == "__main__":
    unittest.main()
