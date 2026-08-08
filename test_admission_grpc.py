"""
End-to-End Test Suite for Admission Controller & Worker Preemption Contracts
===========================================================================
Validates:
- Health Check (SERVING status)
- P1 token bucket rate limit and burst allowance
- Bounded preemption of P2 tasks
- Checkpoint token generation and Resume verification
- Hysteresis throttling on P3 background tasks
"""

import time
import unittest
from admission_controller_grpc import AdmissionControllerServicer, HealthServicer
from p2_worker_stub import WorkerServicer
from proto import admission_pb2, worker_pb2

class TestAdmissionAndPreemption(unittest.TestCase):
    def setUp(self):
        self.controller = AdmissionControllerServicer()
        self.health = HealthServicer()
        self.worker = WorkerServicer()

    def test_01_health_check(self):
        """Verifies Health service returns SERVING."""
        resp = self.health.Check(admission_pb2.HealthCheckRequest(service="admission"))
        self.assertEqual(resp.status, "SERVING")

    def test_02_p1_token_bucket_admission(self):
        """Verifies P1 tokens are granted immediately."""
        req = admission_pb2.AdmitRequest(id="test-p1-1", priority=1, payload="interactive_turn")
        resp = self.controller.Admit(req)
        self.assertEqual(resp.action, "start")
        self.assertEqual(resp.reason, "token")

    def test_03_p2_queuing_and_preemption(self):
        """Verifies P2 tasks are queued and preempted by burst P1 when tokens are exhausted."""
        # 1. Enqueue P2 task
        p2_req = admission_pb2.AdmitRequest(id="test-p2-task", priority=2, payload="code_orchestration")
        p2_resp = self.controller.Admit(p2_req)
        self.assertEqual(p2_resp.action, "queued")

        # 2. Exhaust P1 tokens
        self.controller.p1_bucket.tokens = 0.0

        # 3. Submit P1 request -> triggers preemption of queued P2 task
        p1_urgent = admission_pb2.AdmitRequest(id="test-p1-urgent", priority=1, payload="urgent_chat")
        p1_resp = self.controller.Admit(p1_urgent)
        self.assertEqual(p1_resp.action, "start")
        self.assertEqual(p1_resp.reason, "preempt")
        self.assertTrue(len(p1_resp.checkpoint_token) > 0)

    def test_04_worker_checkpoint_and_resume(self):
        """Verifies Worker Preempt and Resume contracts."""
        preempt_req = worker_pb2.PreemptRequest(task_id="task-404", progress="Step 3/5 complete")
        preempt_resp = self.worker.Preempt(preempt_req)
        token = preempt_resp.checkpoint_token
        self.assertIn("task-404", token)

        # Resume using checkpoint token
        resume_req = worker_pb2.ResumeRequest(checkpoint_token=token)
        resume_resp = self.worker.Resume(resume_req)
        self.assertEqual(resume_resp.status, "RESUMED")

    def test_05_p3_hysteresis_throttling(self):
        """Verifies P3 tasks are admitted under normal load and throttled under high load."""
        p3_req = admission_pb2.AdmitRequest(id="test-p3-dpo", priority=3, payload="vector_compile")
        resp = self.controller.Admit(p3_req)
        self.assertEqual(resp.action, "scheduled")

        # Engage throttle manually
        self.controller.p3_throttled_until = time.time() + 30.0
        throttled_resp = self.controller.Admit(p3_req)
        self.assertEqual(throttled_resp.action, "reject")
        self.assertEqual(throttled_resp.code, "P3_THROTTLED")


if __name__ == '__main__':
    unittest.main()
