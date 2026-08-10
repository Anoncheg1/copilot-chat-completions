# Run locally:
# export PYTHONPATH="/path-to/copilot-sdk/python"
# PYTHONPATH="/home/user/copilot-sdk/python" python3.14 -m pytest test_server.py -v
# pip install -r requirements.txt

import os
os.environ["TESTING"] = "1"

import pytest
from httpx import AsyncClient, ASGITransport

import server


class DummySession:
    async def send_and_wait(self, prompt, timeout=None):
        class Data:
            content = "hello from session"
        class Response:
            data = Data()
        return Response()

    # Provide async context manager protocol to match CopilotClient
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def disconnect(self):
        return None


class DummyClient:
    def __init__(self, *args, **kwargs):
        # accept any constructor args the real client expects
        pass

    # Provide async context manager protocol to match CopilotClient
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def start(self):
        return None

    async def stop(self):
        return None

    async def create_session(self, **kwargs):
        return DummySession()


@pytest.mark.asyncio
async def test_chat_basic_and_model(monkeypatch):
    """Integration-style test: monkeypatch CopilotClient so app lifespan uses a dummy client/session,
    then call the chat completions endpoint and verify reply content and model handling.
    """
    # Patch the CopilotClient class used by the server before triggering the app lifespan
    monkeypatch.setattr(server, "CopilotClient", DummyClient)

    # Ensure any previous globals are cleared
    server.copilot_client = None
    server.copilot_session = None
    server.messages_saved = None

    # Enter the server lifespan context manager to run startup and initialize the dummy client/session
    lifespan_cm = server.lifespan(server.app)
    await lifespan_cm.__aenter__()

    try:
        transport = ASGITransport(app=server.app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            # Basic request (no model) -> default model in response
            r = await ac.post(
                "/v1/chat/completions",
                json={"messages": [{"role": "user", "content": "hi"}]},
            )
            assert r.status_code == 200
            data = r.json()
            assert data["choices"][0]["message"]["content"] == "hello from session"
            assert data["model"] == "gpt-4.1"

            # Request with explicit model -> response echoes requested model
            r2 = await ac.post(
                "/v1/chat/completions",
                json={"messages": [{"role": "user", "content": "hi again"}], "model": "custom-model"},
            )
            assert r2.status_code == 200
            data2 = r2.json()
            assert data2["model"] == "custom-model"
    finally:
        # Exit the lifespan context to shut down the dummy client
        await lifespan_cm.__aexit__(None, None, None)

    # Cleanup globals to avoid leaking state between tests
    server.copilot_client = None
    server.copilot_session = None
    server.messages_saved = None
