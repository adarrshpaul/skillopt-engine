"""Admission gRPC servicer stubs and helpers."""

class AdmissionServiceServicer:
    def Admit(self, request, context):
        raise NotImplementedError()

class HealthServicer:
    def Check(self, request, context):
        raise NotImplementedError()

def add_AdmissionServiceServicer_to_server(servicer, server):
    if hasattr(server, 'add_generic_rpc_handlers'):
        pass

def add_HealthServicer_to_server(servicer, server):
    if hasattr(server, 'add_generic_rpc_handlers'):
        pass
