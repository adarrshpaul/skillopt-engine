import unittest
import time
from admission_controller_grpc import AdmissionControllerServicer
from proto import admission_pb2

class TestAdmissionUnit(unittest.TestCase):
    def setUp(self):
        self.controller = AdmissionControllerServicer()

    def test_p1_token_bucket_grants(self):
        req = admission_pb2.AdmitRequest(id="p1-test", priority=1, payload="turn")
        res = self.controller.Admit(req)
        self.assertEqual(res.action, "start")
        self.assertEqual(res.reason, "token")

    def test_p1_token_bucket_exhaustion(self):
        self.controller.p1_bucket.tokens = 0.0
        self.controller.p1_preempt_budget = 0
        req = admission_pb2.AdmitRequest(id="p1-exhaust", priority=1, payload="turn")
        res = self.controller.Admit(req)
        self.assertEqual(res.action, "reject")
        self.assertEqual(res.code, "P1_RATE_LIMIT")

    def test_p2_queues_task(self):
        req = admission_pb2.AdmitRequest(id="p2-test", priority=2, payload="task")
        res = self.controller.Admit(req)
        self.assertEqual(res.action, "queued")

    def test_p2_queue_full_rejects(self):
        for i in range(50):
            self.controller.p2_queue.put_nowait({"id": f"q-{i}"})
        req = admission_pb2.AdmitRequest(id="p2-overflow", priority=2, payload="overflow")
        res = self.controller.Admit(req)
        self.assertEqual(res.action, "reject")
        self.assertEqual(res.code, "P2_QUEUE_FULL")

    def test_p1_preempts_p2(self):
        self.controller.p2_queue.put_nowait({"id": "task-to-preempt"})
        self.controller.p1_bucket.tokens = 0.0
        self.controller.p1_preempt_budget = 5
        req = admission_pb2.AdmitRequest(id="p1-preemptor", priority=1, payload="urgent")
        res = self.controller.Admit(req)
        self.assertEqual(res.action, "start")
        self.assertEqual(res.reason, "preempt")
        self.assertTrue(len(res.checkpoint_token) > 0)

    def test_preemption_budget_limits(self):
        self.controller.p2_queue.put_nowait({"id": "task-1"})
        self.controller.p1_bucket.tokens = 0.0
        self.controller.p1_preempt_budget = 0
        req = admission_pb2.AdmitRequest(id="p1-no-budget", priority=1, payload="urgent")
        res = self.controller.Admit(req)
        self.assertEqual(res.action, "reject")

    def test_p3_admitted_under_low_util(self):
        self.controller.composite_util = lambda: 0.30
        req = admission_pb2.AdmitRequest(id="p3-test", priority=3, payload="background")
        res = self.controller.Admit(req)
        self.assertEqual(res.action, "scheduled")

    def test_p3_throttled_under_high_util(self):
        self.controller.p3_throttled_until = time.time() + 30.0
        req = admission_pb2.AdmitRequest(id="p3-throttled", priority=3, payload="background")
        res = self.controller.Admit(req)
        self.assertEqual(res.action, "reject")
        self.assertEqual(res.code, "P3_THROTTLED")

    def test_p3_hysteresis_holdoff(self):
        self.controller.p3_throttled_until = time.time() + 10.0
        self.assertFalse(self.controller.can_run_p3())

if __name__ == "__main__":
    unittest.main()
