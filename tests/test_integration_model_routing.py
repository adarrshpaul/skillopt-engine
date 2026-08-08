import unittest
import urllib.request
import json
import sys
sys.path.insert(0, '/Users/adarrsh/workspace')
import model_router

def _http_available(url):
    try:
        req = urllib.request.Request(f"{url}/health")
        with urllib.request.urlopen(req, timeout=2) as resp:
            return resp.status == 200
    except:
        return False

HAS_CODER = _http_available('http://localhost:8800/v1')
HAS_PLANNER = _http_available('http://localhost:8801/v1')

class TestIntegrationModelRouting(unittest.TestCase):

    @unittest.skipUnless(HAS_PLANNER, "Planner model server not running on :8801")
    def test_e2e_planner_responds_on_8801(self):
        url = "http://localhost:8801/v1/chat/completions"
        payload = json.dumps({
            "model": model_router.get_model("planner"),
            "messages": [{"role": "user", "content": "Ping"}]
        }).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)

    @unittest.skipUnless(HAS_CODER, "Coder model server not running on :8800")
    def test_e2e_coder_responds_on_8800(self):
        url = "http://localhost:8800/v1/chat/completions"
        payload = json.dumps({
            "model": model_router.get_model("coder"),
            "messages": [{"role": "user", "content": "Ping"}]
        }).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)

    def test_e2e_model_router_planner_url(self):
        self.assertIn(":8801", model_router.get_url("planner"))
        self.assertEqual(model_router.get_model("planner"), "inclusionAI/Ling-3.0-flash")

    def test_e2e_model_router_coder_url(self):
        self.assertIn(":8800", model_router.get_url("coder"))
        self.assertEqual(model_router.get_model("coder"), "ornith-9b")

if __name__ == "__main__":
    unittest.main()
