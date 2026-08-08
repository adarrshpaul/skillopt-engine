"""Worker gRPC servicer stubs and helpers."""

class WorkerServicer:
    def Preempt(self, request, context):
        raise NotImplementedError()

    def Resume(self, request, context):
        raise NotImplementedError()

def add_WorkerServicer_to_server(servicer, server):
    if hasattr(server, 'add_generic_rpc_handlers'):
        pass
