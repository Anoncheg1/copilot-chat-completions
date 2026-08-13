import sys
import types
import asyncio
import importlib
import pytest

# --- Inject tiny fake fastapi + responses before importing server ---
fastapi_mod = types.ModuleType("fastapi")
class FakeFastAPI:
    def __init__(self, *a, **k):
        pass
    def post(self, *args, **kwargs):
        def decorator(func):
            return func
        return decorator
fastapi_mod.FastAPI = FakeFastAPI
class _BackgroundTasks:
    def add_task(self, *a, **k): pass
fastapi_mod.BackgroundTasks = _BackgroundTasks
sys.modules["fastapi"] = fastapi_mod

responses_mod = types.ModuleType("fastapi.responses")
class JSONResponse:
    def __init__(self, content=None, status_code=200):
        self.content = content
        self.status_code = status_code
        import json as _json
        try:
            self.body = _json.dumps(content).encode() if content is not None else b""
        except Exception:
            # fall back to bytes of repr if content is not JSON-serializable
            self.body = repr(content).encode()
responses_mod.JSONResponse = JSONResponse
sys.modules["fastapi.responses"] = responses_mod

# --- Inject tiny fake copilot SDK pieces ---
copilot_mod = types.ModuleType("copilot")
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
copilot_mod.CopilotClient = DummyCopilotClient
class RuntimeConnection:
    @staticmethod
    def for_stdio(path=None, args=None): return None
copilot_mod.RuntimeConnection = RuntimeConnection
sys.modules["copilot"] = copilot_mod

session_mod = types.ModuleType("copilot.session")
class PermissionHandler:
    @staticmethod
    def approve_all(*a, **k): return True
session_mod.PermissionHandler = PermissionHandler
sys.modules["copilot.session"] = session_mod

rpc_mod = types.ModuleType("copilot._jsonrpc")
class JsonRpcError(Exception): pass
class ProcessExitedError(Exception): pass
rpc_mod.JsonRpcError = JsonRpcError
rpc_mod.ProcessExitedError = ProcessExitedError
sys.modules["copilot._jsonrpc"] = rpc_mod

# Now import the server module (it will pick up the fake modules)
# Ensure any previously-loaded server is removed so the fakes take effect
sys.modules.pop("server", None)
server = importlib.import_module("server")

# Helpers for fake sessions/responses
class FakeResponse:
    def __init__(self, text): self.data = types.SimpleNamespace(content=text)

class FakeSession:
    def __init__(self, reply_text="ok"): self.reply_text = reply_text
    async def send_and_wait(self, prompt, timeout=None):
        return FakeResponse(self.reply_text)
    async def disconnect(self): pass

class RaisingSession:
    async def send_and_wait(self, *a, **k):
        raise Exception("You have exceeded your monthly quota")
    async def disconnect(self): pass

@pytest.mark.asyncio
async def test_chat_completions_success():
    server.copilot_session = FakeSession("reply-from-fake")
    request = {"messages": [{"role": "user", "content": "Hello"}]}
    resp = await server.chat_completions(request, None)
    assert resp.content["choices"][0]["message"]["content"] == "reply-from-fake"
    assert resp.content["model"] == request.get("model", "gpt-4.1")

@pytest.mark.asyncio
async def test_chat_completions_retry_on_error():
    # initial session raises; create_new_session returns a working session
    server.copilot_session = RaisingSession()
    async def make_new(copilot_client): return FakeSession("retried-reply")
    server.create_new_session = make_new
    request = {"messages": [{"role": "user", "content": "Hi again"}]}
    resp = await server.chat_completions(request, None)
    assert resp.content["choices"][0]["message"]["content"] == "retried-reply"
