#!/usr/bin/env python3
"""Test PTY functionality with E2B - minimal test."""
import sys
import time
import threading
from e2b_code_interpreter import Sandbox
from e2b import PtySize

# Get sandbox ID
import os
try:
    cache_file = os.path.expanduser("~/.claudeswarm/last_sandbox_id")
    with open(cache_file, 'r') as f:
        sandbox_id = f.read().strip()
except FileNotFoundError:
    print("No cached sandbox found")
    sys.exit(1)

print(f"Connecting to sandbox: {sandbox_id}")
sandbox = Sandbox.connect(sandbox_id)
print("Connected!")

# Create PTY
print("Creating PTY...")
pty = sandbox.pty.create(
    size=PtySize(rows=24, cols=80),
    cwd="/workspace"
)
print(f"PTY created with PID: {pty.pid}")
print(f"PTY attributes: {[x for x in dir(pty) if not x.startswith('_')]}")

# Test: Start bash and wait for output
print("\nStarting bash...")
sandbox.pty.send_stdin(pty.pid, b"bash -i\n")
time.sleep(0.5)

# Try to iterate and collect output
print("Reading output for 3 seconds...")
output_count = 0
stop = False

def read_output():
    global output_count, stop
    try:
        for event in pty:
            if stop:
                break
            output_count += 1
            print(f"\n--- Event #{output_count} ---")
            print(f"Type: {type(event)}")
            if hasattr(event, 'data'):
                print(f"Data (bytes): {event.data}")
                try:
                    print(f"Data (str): {event.data.decode('utf-8', errors='replace')}")
                except:
                    pass
            print(f"Full event: {event}")
    except Exception as e:
        print(f"Iterator error: {e}")
        import traceback
        traceback.print_exc()

thread = threading.Thread(target=read_output, daemon=True)
thread.start()

# Wait and send some commands
time.sleep(2)
print("\n\nSending 'echo hello' command...")
sandbox.pty.send_stdin(pty.pid, b"echo hello\n")
time.sleep(1)

print("\n\nSending 'pwd' command...")
sandbox.pty.send_stdin(pty.pid, b"pwd\n")
time.sleep(1)

stop = True
time.sleep(0.5)

print(f"\n\nTotal events received: {output_count}")

# Cleanup
print("Killing PTY...")
try:
    sandbox.pty.kill(pty.pid)
except:
    pass
print("Done!")
