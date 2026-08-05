# Run locally:
# export TESTING=1
# export PYTHONPATH="/path-to/copilot-sdk/python"
# pip install -r requirements.txt

import os
os.environ["TESTING"] = "1"

import pytest
from httpx import AsyncClient, ASGITransport
import server

class DummySession:
    async def send_and_wait(self, prompt, timeout=None):
        class D:
            content = "hello"
        class R:
            data = D()
        return R()
    async def disconnect(self):
        pass

server.copilot_session = DummySession()
@pytest.mark.asyncio
async def test_chat():
    transport = ASGITransport(app=server.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.post("/v1/chat/completions",
 json={"messages":[{"role":"user","content":"hi"}]})
    assert r.status_code == 200
    assert r.json()["choices"][0]["message"]["content"] == "hello"
