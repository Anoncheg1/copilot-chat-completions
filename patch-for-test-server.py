# replacement for `from copilot....` in server.py
CopilotClient = None
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
