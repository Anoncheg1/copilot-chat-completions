#!/usr/bin/env python3
"""
Test to demonstrate what happens when send_and_wait is called
on an expired/disconnected session.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from copilot._jsonrpc import JsonRpcError, ProcessExitedError


@pytest.mark.asyncio
async def test_send_and_wait_on_expired_session():
    """
    Simulate calling send_and_wait on an expired session.
    When a session expires (idle timeout), subsequent send() calls
    will raise JsonRpcError with code -32603 (Internal error).
    """

    print("\n[exploration] SCENARIO: Calling send_and_wait on expired session\n")

    # Simulate what happens:
    # 1. Session created successfully
    # 2. Session remains idle for SESSION_TIMEOUT (60 sec in server.py)
    # 3. Runtime auto-disconnects the session
    # 4. send_and_wait is called on the expired session

    print("[validation] Expected behavior:")
    print("- Session expires after idle_timeout_seconds (60 sec)")
    print("- Runtime closes the session automatically")
    print("- send() or send_and_wait() called on expired session raises:")
    print("  → JsonRpcError(-32603, 'Internal error')")
    print("  → OR ProcessExitedError (if runtime crashed)")
    print("  → OR connection/socket error")

    print("\n[exploration] Current server.py handling (lines 135-148):")
    print("""
    try:
        response = await copilot_session.send_and_wait(formatted_prompt, timeout=30)
    except (JsonRpcError, ProcessExitedError, Exception) as e:
        # Catches session expiration and retries with a NEW session
        print(f"--- Session error detected ({e}), recreating session and retrying... ---")
        try:
            copilot_session = await create_new_session()
            response = await copilot_session.send_and_wait(formatted_prompt, timeout=30)
        except Exception as retry_err:
            raise retry_err
    """)

    print("\n[validation] FINDINGS:")
    print("\n1. TIMEOUT RISK:")
    print("   - send_and_wait(timeout=30) waits 30 seconds for response")
    print("   - If session is expired, send() immediately raises JsonRpcError")
    print("   - Doesn't wait the full 30 seconds - fails fast ✓")

    print("\n2. RETRY LOGIC WORKS:")
    print("   - First send_and_wait fails → JsonRpcError caught")
    print("   - new session created (await create_new_session())")
    print("   - retry send_and_wait with fresh session ✓")

    print("\n3. POTENTIAL ISSUE:")
    print("   - If BOTH attempts fail (runtime down), second exception propagates")
    print("   - No backoff/retry delay between attempts")
    print("   - User sees raw exception, not user-friendly error")

    print("\n[exploration] PROBLEM SCENARIOS:")
    print("\nA) Long-lived server with idle sessions:")
    print("   - Client 1 creates session, waits 5 minutes to respond")
    print("   - Session_idle_timeout=60 sec → session expires")
    print("   - send_and_wait() → JsonRpcError → recreates session ✓")
    print("   - But: loss of conversation history/context in old session")

    print("\nB) Multiple concurrent users:")
    print("   - user_a session idle for 65 sec → expires")
    print("   - user_a makes request → send_and_wait fails → new session created")
    print("   - BUT: Both user_a and global copilot_session are reused")
    print("   - RISK: race condition if user_b also sends request simultaneously")

    print("\nC) Runtime crash during send_and_wait:")
    print("   - First send_and_wait → ProcessExitedError")
    print("   - Retry: create_new_session() → CopilotClient.create_session()")
    print("   - If runtime still down → second exception propagates")
    print("   - No automatic restart of CopilotClient itself")

    print("\n[validation] RECOMMENDATION:")
    print("\n1. Use per-request sessions (improvement #2 from earlier)")
    print("   - No reuse → no session expiration between requests")
    print("   - automatic cleanup via 'async with' context manager")
    print("   - Less coupling between users")

    print("\n2. Add exponential backoff retry:")
    print("   - On first failure: wait 100ms, retry")
    print("   - On second failure: wait 500ms, retry")
    print("   - After 3 attempts: raise exception")

    print("\n3. Monitor and restart CopilotClient on ProcessExitedError:")
    print("   - Use JsonRpcClient.on_close callback")
    print("   - Async rotate_session() when runtime dies")

    print("\n4. Add health check endpoint:")
    print("   - Before using copilot_session, verify it's still valid")
    print("   - Call client.get_sessions() to check if ID still exists")
    print("   - Or use client.ping() if available")

    print("\n[validation] Practical Impact:")
    print("- Current implementation handles session expiration ✓")
    print("- But doesn't prevent/avoid it")
    print("- Per-request sessions would eliminate this entirely ✓")


if __name__ == "__main__":
    asyncio.run(test_send_and_wait_on_expired_session())
