# replacement for `from copilot....` in server.py
class DummyCopilotClient:
    # Implement async context manager protocol expected by server.lifespan
    def __init__(self, *args, **kwargs):
        pass
    async def __aenter__(self):
        return self
    async def __aexit__(self, exc_type, exc, tb):
        return None
    async def start(self): pass
    async def stop(self): pass
    async def create_session(self, *a, **k): return None
CopilotClient = DummyCopilotClient
class RuntimeConnection:
    @staticmethod
    def for_stdio(path=None, args=None):
        return None
class PermissionHandler:
    @staticmethod
    def approve_all(*args, **kwargs):
        return True
class JsonRpcError(Exception):
    pass
class ProcessExitedError(Exception):
    pass
