#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (C) 2026 github.com/Anoncheg1,codeberg.org/Anoncheg
# Author: <github.com/Anoncheg1,codeberg.org/Anoncheg>
# Created: 2026-08-05
# License: AGPLv3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Version: 0.1

# Doc: https://github.com/github/copilot-sdk/blob/main/python/README.md
# COPILOT_CLI_PATH
# Commentary:
# To run: PYTHONPATH="/path-to/copilot-sdk/python" uvicorn server:app --host 127.0.0.1 --port 8000 --reload
#
# TODO: use ‎CopilotClient.ping to keep connection
# OLD: replaced with PYTHONPATH=
# import sys
# SDK_PATH = "/home/rtorrent/copilot-sdk/python"
# sys.path.insert(0, SDK_PATH)

import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, BackgroundTasks
from fastapi.responses import JSONResponse
from copilot import CopilotClient, RuntimeConnection
from copilot.session import PermissionHandler
from copilot._jsonrpc import JsonRpcError, ProcessExitedError
SEND_AND_WAIT = 300.0 # secs
copilot_client = None
copilot_session = None

async def create_new_session():
    return await copilot_client.create_session(
        model="gpt-5-mini",
        # reasoning_effort="high",
        on_permission_request=PermissionHandler.approve_all,
        streaming=False,
        infinite_sessions={"enabled": False}
    )

@asynccontextmanager
async def lifespan(app: FastAPI):
    global copilot_client, copilot_session
    #  use logged-in user for authentication: use_logged_in_user=True, github_token is not provided here
    copilot_client = CopilotClient(
        connection=RuntimeConnection.for_stdio(
            path="node",
            args=["/usr/lib/node_modules/@github/copilot/npm-loader.js"]
        ),
        session_idle_timeout_seconds=300
    )
    await copilot_client.start()
    copilot_session = await create_new_session()
    print("--- Copilot Client & Session Initialized ---")

    yield

    if copilot_session:
        try: await copilot_session.disconnect()
        except: pass
    if copilot_client:
        await copilot_client.stop()
        print("--- Copilot Client Stopped ---")

app = FastAPI(lifespan=lifespan)

async def rotate_session(old_session):
    global copilot_session
    try:
        await old_session.disconnect()
    except:
        pass
    print("--- Session Re-Initialized ---")
    copilot_session = await create_new_session()

@app.post("/v1/chat/completions")
async def chat_completions(request: dict, background_tasks: BackgroundTasks):
    global copilot_session

    messages = request.get("messages", [])
    current_session = copilot_session

    # Flatten all incoming messages into a single chat-formatted prompt string
    formatted_prompt = "\n".join([
        f"{msg.get('role', 'user').capitalize()}: {msg.get('content', '')}"
        for msg in messages
    ])
    print("messages", messages)
    print("formatted_prompt", formatted_prompt)

    # Send as one rapid payload and wait for the response
    response = await current_session.send_and_wait(formatted_prompt, timeout = SEND_AND_WAIT)
    try:
        # Attempt to send with the current session
        response = await current_session.send_and_wait(formatted_prompt)

    except (JsonRpcError, ProcessExitedError): # Connection lost
        # Check if it's a missing/stale session error
        print("--- Stale session detected, recreating session and retrying... ---")
        copilot_session = await create_new_session()
        current_session = copilot_session
        # Retry request with the brand new session
        response = await current_session.send_and_wait(formatted_prompt)


    assistant_reply = response.data.content if response and response.data else "No response generated."

    # Rotate session asynchronously in the background
    background_tasks.add_task(rotate_session, current_session)

    return JSONResponse(content={
        "id": "chatcmpl-copilot",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": request.get("model", "gpt-4.1"),
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": assistant_reply},
            "finish_reason": "stop"
        }]
    })
