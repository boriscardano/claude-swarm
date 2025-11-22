#!/usr/bin/env python3
"""Check token in specific sandbox."""
import asyncio
from e2b_code_interpreter import Sandbox

async def check():
    # The sandbox I deployed with OAuth token
    sandbox_id = "iohibsaj0nehsegs5o0de"

    print(f"Connecting to sandbox: {sandbox_id}")
    sandbox = await asyncio.to_thread(Sandbox.connect, sandbox_id)
    print("Connected!\n")

    print("Checking /root/.bashrc:")
    result = await asyncio.to_thread(sandbox.run_code, "!cat /root/.bashrc | grep CLAUDE || echo 'Not found'")
    if hasattr(result, 'logs') and result.logs and result.logs.stdout:
        for line in result.logs.stdout:
            print(line.rstrip())

if __name__ == "__main__":
    asyncio.run(check())
