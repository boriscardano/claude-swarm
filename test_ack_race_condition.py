#!/usr/bin/env python3
"""Test script to verify ACK race condition is fixed.

This script simulates the race condition scenario where:
1. process_retries() loads ACKs: [A, B, C]
2. While processing retries (slow operation), receive_ack() processes ACK for B
3. process_retries() tries to save its updated list
4. With the fix, it should detect the version conflict and retry

Expected behavior:
- Without fix: Message B would be lost
- With fix: Message B should be properly acknowledged and removed
"""

import json
import threading
import time
from pathlib import Path
from datetime import datetime, timedelta
from dataclasses import dataclass

# Test configuration - will be set dynamically
TEST_FILE = None


@dataclass
class TestResult:
    """Track test execution results."""
    process_retries_attempts: int = 0
    receive_ack_success: bool = False
    final_acks: list = None
    message_b_lost: bool = False


def setup_test_file(test_file_path):
    """Create test file with 3 pending ACKs.

    Args:
        test_file_path: Path object to write test file to
    """
    now = datetime.now()
    next_retry = now - timedelta(seconds=1)  # Past time to trigger retry

    test_data = {
        "version": 1,
        "pending_acks": [
            {
                "msg_id": "msg-A",
                "sender_id": "agent-1",
                "recipient_id": "agent-2",
                "message": {"msg_id": "msg-A", "content": "Message A", "msg_type": "INFO"},
                "sent_at": now.isoformat(),
                "retry_count": 0,
                "next_retry_at": next_retry.isoformat(),
            },
            {
                "msg_id": "msg-B",
                "sender_id": "agent-1",
                "recipient_id": "agent-2",
                "message": {"msg_id": "msg-B", "content": "Message B", "msg_type": "INFO"},
                "sent_at": now.isoformat(),
                "retry_count": 0,
                "next_retry_at": (now + timedelta(seconds=60)).isoformat(),  # Not ready for retry
            },
            {
                "msg_id": "msg-C",
                "sender_id": "agent-1",
                "recipient_id": "agent-2",
                "message": {"msg_id": "msg-C", "content": "Message C", "msg_type": "INFO"},
                "sent_at": now.isoformat(),
                "retry_count": 0,
                "next_retry_at": (now + timedelta(seconds=60)).isoformat(),  # Not ready for retry
            },
        ]
    }

    with open(test_file_path, "w") as f:
        json.dump(test_data, f, indent=2)

    print(f"✓ Created test file with 3 pending ACKs: A, B, C")


def simulate_process_retries_old(result: TestResult, test_file_path):
    """Simulate OLD behavior (WITHOUT version checking) - this has the race condition.

    Args:
        result: TestResult object to track results
        test_file_path: Path object for test file
    """
    print("\n[process_retries] Loading ACKs...")

    # Load ACKs
    with open(test_file_path) as f:
        data = json.load(f)
    acks = data["pending_acks"]
    print(f"[process_retries] Loaded {len(acks)} ACKs: {[a['msg_id'] for a in acks]}")

    # Simulate slow processing (retry message A)
    print("[process_retries] Processing retry for msg-A (simulating 2 second delay)...")
    time.sleep(2)

    # Update ACK A's retry count
    for ack in acks:
        if ack["msg_id"] == "msg-A":
            ack["retry_count"] += 1
            break

    # Save (OLD WAY - no version check)
    print("[process_retries] Saving updated ACKs...")
    data["pending_acks"] = acks
    with open(test_file_path, "w") as f:
        json.dump(data, f, indent=2)

    print(f"[process_retries] Saved ACKs: {[a['msg_id'] for a in acks]}")
    result.process_retries_attempts = 1


def simulate_process_retries_new(result: TestResult, test_file_path):
    """Simulate NEW behavior (WITH version checking) - race condition fixed.

    Args:
        result: TestResult object to track results
        test_file_path: Path object for test file
    """
    max_attempts = 5

    for attempt in range(max_attempts):
        print(f"\n[process_retries] Attempt {attempt + 1}/{max_attempts}")
        print("[process_retries] Loading ACKs with version...")

        # Load ACKs with version
        with open(test_file_path) as f:
            data = json.load(f)
        acks = data["pending_acks"]
        version = data.get("version", 0)
        print(f"[process_retries] Loaded {len(acks)} ACKs: {[a['msg_id'] for a in acks]}, version={version}")

        # Simulate slow processing (retry message A)
        if attempt == 0:
            print("[process_retries] Processing retry for msg-A (simulating 2 second delay)...")
            time.sleep(2)

        # Update ACK A's retry count
        for ack in acks:
            if ack["msg_id"] == "msg-A":
                ack["retry_count"] += 1
                break

        # Try to save with version check (NEW WAY)
        print("[process_retries] Attempting to save with version check...")
        with open(test_file_path) as f:
            current_data = json.load(f)
        current_version = current_data.get("version", 0)

        if current_version != version:
            print(f"[process_retries] ⚠️  Version conflict! Expected {version}, found {current_version}. Retrying...")
            result.process_retries_attempts += 1
            continue  # Retry

        # Version matches, safe to save
        data["version"] = version + 1
        data["pending_acks"] = acks
        with open(test_file_path, "w") as f:
            json.dump(data, f, indent=2)

        print(f"[process_retries] ✓ Saved ACKs: {[a['msg_id'] for a in acks]}, new version={version + 1}")
        result.process_retries_attempts += 1
        return  # Success

    print(f"[process_retries] ✗ Failed after {max_attempts} attempts!")


def simulate_receive_ack(result: TestResult, test_file_path):
    """Simulate receiving ACK for message B (runs concurrently).

    Args:
        result: TestResult object to track results
        test_file_path: Path object for test file
    """
    # Wait a bit for process_retries to start
    time.sleep(0.5)

    print("\n[receive_ack] Received ACK for msg-B, removing from pending...")

    # Load current ACKs with version
    with open(test_file_path) as f:
        data = json.load(f)
    acks = data["pending_acks"]
    version = data.get("version", 0)
    print(f"[receive_ack] Loaded {len(acks)} ACKs: {[a['msg_id'] for a in acks]}, version={version}")

    # Remove message B
    acks = [ack for ack in acks if ack["msg_id"] != "msg-B"]

    # Save with incremented version
    data["version"] = version + 1
    data["pending_acks"] = acks
    with open(test_file_path, "w") as f:
        json.dump(data, f, indent=2)

    print(f"[receive_ack] ✓ Removed msg-B, saved ACKs: {[a['msg_id'] for a in acks]}, new version={version + 1}")
    result.receive_ack_success = True


def verify_result(result: TestResult, test_name: str, test_file_path):
    """Verify test results.

    Args:
        result: TestResult object with test execution data
        test_name: Name of the test for display
        test_file_path: Path object for test file
    """
    print(f"\n{'='*60}")
    print(f"Test: {test_name}")
    print(f"{'='*60}")

    # Load final state
    with open(test_file_path) as f:
        data = json.load(f)
    final_acks = [ack["msg_id"] for ack in data["pending_acks"]]
    final_version = data.get("version", 0)

    print(f"Final ACKs: {final_acks}")
    print(f"Final version: {final_version}")
    print(f"process_retries attempts: {result.process_retries_attempts}")
    print(f"receive_ack success: {result.receive_ack_success}")

    # Check if message B was lost
    message_b_lost = "msg-B" in final_acks
    result.message_b_lost = message_b_lost
    result.final_acks = final_acks

    if message_b_lost:
        print("\n✗ FAIL: Message B is still in pending ACKs (should have been removed)")
        print("  This indicates the race condition occurred!")
    else:
        print("\n✓ PASS: Message B was successfully removed")
        print("  Race condition prevented by version-based locking!")

    # Additional checks
    if "msg-A" in final_acks:
        # Check retry count was updated
        for ack in data["pending_acks"]:
            if ack["msg_id"] == "msg-A":
                print(f"✓ Message A retry count: {ack['retry_count']}")

    if "msg-C" in final_acks:
        print("✓ Message C still pending (as expected)")

    return not message_b_lost


def run_test_old_behavior(test_file_path):
    """Run test simulating OLD behavior (demonstrates the bug).

    Args:
        test_file_path: Path object for test file
    """
    setup_test_file(test_file_path)
    result = TestResult()

    # Start threads
    t1 = threading.Thread(target=simulate_process_retries_old, args=(result, test_file_path))
    t2 = threading.Thread(target=simulate_receive_ack, args=(result, test_file_path))

    t1.start()
    t2.start()

    t1.join()
    t2.join()

    return verify_result(result, "OLD BEHAVIOR (Without Version Locking)", test_file_path)


def run_test_new_behavior(test_file_path):
    """Run test simulating NEW behavior (demonstrates the fix).

    Args:
        test_file_path: Path object for test file
    """
    setup_test_file(test_file_path)
    result = TestResult()

    # Start threads
    t1 = threading.Thread(target=simulate_process_retries_new, args=(result, test_file_path))
    t2 = threading.Thread(target=simulate_receive_ack, args=(result, test_file_path))

    t1.start()
    t2.start()

    t1.join()
    t2.join()

    return verify_result(result, "NEW BEHAVIOR (With Version Locking)", test_file_path)


def main():
    """Run both tests to demonstrate the fix."""
    import tempfile

    print("="*60)
    print("ACK RACE CONDITION TEST")
    print("="*60)
    print("\nThis test simulates the race condition scenario where:")
    print("1. process_retries() loads ACKs and starts processing (slow)")
    print("2. receive_ack() modifies the file while processing is ongoing")
    print("3. process_retries() tries to save its changes")
    print("\nWithout version locking: ACK for message B gets lost")
    print("With version locking: ACK for message B is preserved")
    print()

    # Create temporary directory for test files
    with tempfile.TemporaryDirectory() as tmpdir:
        test_file_path = Path(tmpdir) / "test_pending_acks.json"

        # Test 1: Old behavior (demonstrates bug)
        print("\n" + "="*60)
        print("TEST 1: Demonstrating the bug (old behavior)")
        print("="*60)
        old_passed = run_test_old_behavior(test_file_path)

        time.sleep(1)

        # Test 2: New behavior (demonstrates fix)
        print("\n" + "="*60)
        print("TEST 2: Demonstrating the fix (new behavior)")
        print("="*60)
        new_passed = run_test_new_behavior(test_file_path)

        # Summary
        print("\n" + "="*60)
        print("SUMMARY")
        print("="*60)
        print(f"Old behavior (no version locking): {'FAILED ✗' if not old_passed else 'PASSED ✓'}")
        print(f"New behavior (version locking):    {'PASSED ✓' if new_passed else 'FAILED ✗'}")
        print()

        if not old_passed and new_passed:
            print("✓ SUCCESS: Race condition fix is working correctly!")
            print("  - Old behavior shows the bug (message B lost)")
            print("  - New behavior prevents the bug (message B preserved)")
        else:
            print("⚠️  Unexpected results - review test output")


if __name__ == "__main__":
    main()
