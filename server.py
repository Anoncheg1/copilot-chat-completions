#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (C) 2026 github.com/Anoncheg1,codeberg.org/Anoncheg
# Author: <github.com/Anoncheg1,codeberg.org/Anoncheg>
# Created: 2026-08-05
# License: AGPLv3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Version: 0.2

# License Of Third-Party Components:
# This file / project utilizes an SDK provided under the MIT License:
#     - github/copilot-sdk (Copyright (C) Copyright GitHub, Inc.)
#     See the 'LICENSE-MIT' file in the root directory for full MIT terms.

### Commentary:

# Usage: PYTHONPATH="/path-to/copilot-sdk/python" uvicorn server:app --host 127.0.0.1 --port 8000 --reload

# Documentation of copilot-sdk: https://github.com/github/copilot-sdk/blob/main/python/README.md

### How this works:
# It crete connection to copilot CLI with help of copilot-sdk as "client" and "session"
# When receiving request we save it and check if request is same as saved, then
#  we send() only the last message. If messages is not equeal to saved, we
#  create new session.
# We compare -2 of messages without new user request and without previous
#  answer, because previous answer frequently changed by client to own format.
# If session expired we try to reconnect once.

### TODO:
# - use ‎CopilotClient.ping to keep connection
# - hardcoded "/usr/lib/node_modules/@github/copilot/npm-loader.js". Instead of
#   hardcoding path="node" and args to npm-loader.js, use
#   RuntimeConnection.for_stdio(...)  or let CopilotClient pick the bundled
#   runtime. Respect COPILOT_CLI_PATH and COPILOT_CLI_* env vars described in
#   README to avoid brittle filesystem assumptions.  README documents
#   COPILOT_CLI_PATH and RuntimeConnection helper methods (README lines ~52–60,
#   ~214–219).

### OLD: replaced with PYTHONPATH=
# import sys
# SDK_PATH = "/home/rtorrent/copilot-sdk/python"
# sys.path.insert(0, SDK_PATH)
import os
import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, BackgroundTasks
from fastapi.responses import JSONResponse
from copilot import CopilotClient, RuntimeConnection, StopError
from copilot.session import PermissionHandler
from copilot._jsonrpc import JsonRpcError, ProcessExitedError
SESSION_TIMEOUT = 1500 # 25 min
SEND_AND_WAIT_TIMEOUT = 300.0 # secs
copilot_client = None
copilot_session = None
messages_saved = None # string or list

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

    # use logged-in user for authentication: use_logged_in_user=True, github_token is not provided here
    # Use CopilotClient's async context manager for automatic start/stop/cleanup
    try:
        async with CopilotClient(
            connection=RuntimeConnection.for_stdio(
                path="node",
                args=["/usr/lib/node_modules/@github/copilot/npm-loader.js"]
            ),
            session_idle_timeout_seconds=SESSION_TIMEOUT
        ) as client:
            copilot_client = client
            # create an initial session (kept for compatibility with existing logic)
            copilot_session = await create_new_session()
            print("--- lifespan: Copilot Client & Session Initialized ---")
            try:
                yield
            finally:
                # clear references; the CopilotClient context manager ensures proper stop
                copilot_session = None
                copilot_client = None
                print("--- lifespan: Copilot Client Stopped ---")
    except* StopError as e:
        pass

app = FastAPI(lifespan=lifespan)

async def rotate_session(old_session):
    global copilot_session, messages_saved
    messages_saved = None
    try:
        await old_session.disconnect()
    except:
        pass
    print("--- Session Re-Initialized ---")
    copilot_session = await create_new_session()

@app.post("/v1/chat/completions")
async def chat_completions(request: dict, background_tasks: BackgroundTasks):
    global copilot_session, messages_saved

    messages = request.get("messages", [])
    messages_content = [m.get("content", "") for m in messages]
    messages_content = ["".join(m.split()) for m in messages_content] # remove spaces and new lines


    if len(messages_content) > 2 and messages_content[:-2] == messages_saved:
        # same session: use only last
        print("chat_completions: Same session")
        messages = [messages[-1]]
        # print("wtf1")


    # if old session but with new messages
    elif messages_saved and len(messages_content) > 2 and messages_content[:-2] != messages_saved:
        print("--- Messages changed we re-create session ---")
        await rotate_session(copilot_session) # disconnect and connect
        # copilot_session = await create_new_session() # initialized
        # print("wtf2")
    # else:     # new session

    # Flatten all incoming messages into a single chat-formatted prompt string
    formatted_prompt = "\n".join([
        f"{msg.get('role', 'user').capitalize()}: {msg.get('content', '')}"
        for msg in messages
    ])

    # print("messages", messages)
    print("formatted_prompt", formatted_prompt)

    # Send as one rapid payload and wait for the response
    try:
        # Attempt to send with the current session
        response = await copilot_session.send_and_wait(formatted_prompt, timeout=SEND_AND_WAIT_TIMEOUT)

    except TimeoutError as e:
        # Timeouts indicate the session did not become idle in time. This is
        # usually a slow assistant or long-running work, not a session expiry.
        # Log and return 504 Gateway Timeout to the client rather than recreating.
        print(f"--- Session timeout detected: {e} ---")
        return JSONResponse(status_code=504, content={"error": f"Timeout waiting for session idle: {e}"})
    except (JsonRpcError, ProcessExitedError) as e:
        # Catch JsonRpcError (which houses the -32603 session not found error)
        # or any other unexpected connection/process drops.
        print(f"--- Session error detected ({e}), type ({type(e)}), recreating session and retrying... ---")
        try:
            # 1. Re-create the session
            copilot_session = await create_new_session()

            # 2. Retry request with the brand new session
            response = await copilot_session.send_and_wait(formatted_prompt, timeout=SEND_AND_WAIT_TIMEOUT)

        except Exception as retry_err:
            print(f"--- Retry failed: {retry_err} ---")
            raise retry_err

    except Exception as e:
        print(f"--- Some error from server: {e} type {type(e)} ---")
        return JSONResponse(status_code=400, content={"error": f"Error from copilot-cli: {e}"})

    assistant_reply = response.data.content if response and response.data else "No response generated."

    # old:
    #     # Rotate session asynchronously in the background
    #     background_tasks.add_task(rotate_session, copilot_session)

    # save request
    messages_saved = messages_content

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
