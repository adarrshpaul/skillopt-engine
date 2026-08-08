import unittest
import sys
sys.path.insert(0, '/Users/adarrsh/workspace')

def _grpc_available(port):
    try:
        import grpc
        channel = grpc.insecure_channel(f'localhost:{port}')
        grpc.channel_ready_future(channel).result(timeout=2)
        return True
    except:
        return False

class TestIntegrationAdmissionWorker(unittest.TestCase):

    @unittest.skipUnless(_grpc_available(50051), "Admission controller not running on :50051")
    def test_e2e_p1_admit_via_grpc(self):
        import grpc
        from proto import admission_pb2, admission_pb2_grpc
        channel = grpc.insecure_channel('localhost:50051')
        stub = admission_pb2_grpc.AdmissionServiceStub(channel)
        req = admission_pb2.AdmitRequest(id="e2e-p1", priority=1, payload="interactive")
        res = stub.Admit(req)
        self.assertIn(res.action, ["start", "reject"])

    @unittest.skipUnless(_grpc_available(50051), "Admission controller not running on :50051")
    def test_e2e_p2_queue_via_grpc(self):
        import grpc
        from proto import admission_pb2, admission_pb2_grpc
        channel = grpc.insecure_channel('localhost:50051')
        stub = admission_pb2_grpc.AdmissionServiceStub(channel)
        req = admission_pb2.AdmitRequest(id="e2e-p2", priority=2, payload="orchestration")
        res = stub.Admit(req)
        self.assertIn(res.action, ["queued", "start", "reject"])

    @unittest.skipUnless(_grpc_available(50052), "P2 Worker not running on :50052")
    def test_e2e_worker_preempt_and_resume(self):
        import grpc
        from proto import worker_pb2, worker_pb2_grpc
        channel = grpc.insecure_channel('localhost:50052')
        stub = worker_pb2_grpc.WorkerStub(channel)
        
        preempt_req = worker_pb2.PreemptRequest(task_id="e2e-task-1", progress="Step 2/4")
        preempt_res = stub.Preempt(preempt_req)
        token = preempt_res.checkpoint_token
        self.assertTrue(len(token) > 0)

        resume_req = worker_pb2.ResumeRequest(checkpoint_token=token)
        resume_res = stub.Resume(resume_req)
        self.assertEqual(resume_res.status, "RESUMED")

    @unittest.skipUnless(_grpc_available(50051), "Admission controller not running on :50051")
    def test_e2e_health_check(self):
        import grpc
        from proto import admission_pb2, admission_pb2_grpc
        channel = grpc.insecure_channel('localhost:50051')
        stub = admission_pb2_grpc.HealthStub(channel)
        res = stub.Check(admission_pb2.HealthCheckRequest(service="admission"))
        self.assertEqual(res.status, "SERVING")

if __name__ == "__main__":
    unittest.main()
