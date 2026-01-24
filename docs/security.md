# Security Documentation

Security considerations, best practices, and known limitations for Claude Swarm.

---

## Table of Contents

1. [Trust Model](#trust-model)
2. [Threat Model](#threat-model)
3. [Security Features](#security-features)
4. [Known Limitations](#known-limitations)
5. [Best Practices](#best-practices)
6. [Authentication](#authentication)
7. [Access Control](#access-control)
8. [Data Security](#data-security)
9. [Audit and Logging](#audit-and-logging)
10. [Incident Response](#incident-response)

---

## Trust Model

### Assumptions

Claude Swarm operates under a **trusted environment** model:

1. **Single User Environment:**
   - All agents run under the same user account
   - Agents are on the same physical/virtual machine
   - Shared file system access

2. **Trusted Agents:**
   - All agents are legitimate Claude Code instances
   - No malicious or compromised agents
   - Agents follow the coordination protocol

3. **Trusted Communication:**
   - tmux server is trusted
   - File system is trusted (no malicious modifications)
   - No network communication (all local)

### Scope

This security model is designed for:
- **Development environments** - Single developer working locally
- **Trusted teams** - Small teams on shared workstations
- **Isolated environments** - Containers, VMs with controlled access

**NOT designed for:**
- Multi-tenant environments
- Untrusted networks
- Production systems with sensitive data
- Scenarios with potentially malicious actors

---

## Threat Model

### Threats In Scope

1. **Accidental Conflicts:**
   - Concurrent file editing
   - Race conditions in lock acquisition
   - Message delivery failures

2. **Process Failures:**
   - Agent crashes with held locks
   - Stale agents in registry
   - Corrupted state files

3. **Human Error:**
   - Incorrect configuration
   - Manual file modifications
   - Accidental lock releases

### Threats Out of Scope

1. **Malicious Agents:**
   - Intentionally corrupting files
   - Denial of service attacks
   - Lock hijacking

2. **External Attacks:**
   - Network-based attacks (no network component)
   - System-level compromises
   - Privilege escalation

3. **Data Exfiltration:**
   - Unauthorized access to files
   - Message interception
   - Log tampering

---

## Security Features

### 1. File Locking

**Protection:** Prevents concurrent editing conflicts

**Mechanism:**
- Exclusive file creation (`open(mode='x')`)
- Atomic operations (temp file + rename)
- Ownership verification on release

**Limitations:**
- No authentication - any agent can claim any ID
- Advisory locks only - agents can bypass if malicious
- No encryption of lock files

**Example:**

```python
from claudeswarm.locking import LockManager

lm = LockManager()

# Atomic lock acquisition
success, conflict = lm.acquire_lock(
    filepath="sensitive_file.py",
    agent_id="agent-1",
    reason="critical update"
)

if success:
    try:
        # Work is protected by lock
        modify_file("sensitive_file.py")
    finally:
        # Always release
        lm.release_lock("sensitive_file.py", "agent-1")
```

---

### 2. Rate Limiting

**Protection:** Prevents message spam and resource exhaustion

**Mechanism:**
- 10 messages per agent per minute
- Sliding window implementation
- Soft limit (returns failure, doesn't crash)

**Limitations:**
- Can be bypassed by changing agent ID
- No global rate limiting
- Memory-based (resets on restart)

**Example:**

```python
from claudeswarm.messaging import send_message, MessageType

# Will fail if limit exceeded
msg = send_message(
    sender_id="agent-1",
    recipient_id="agent-2",
    message_type=MessageType.INFO,
    content="Status update"
)

if msg is None:
    # Rate limit exceeded
    print("Too many messages, slow down")
```

---

### 3. Stale Lock Detection

**Protection:** Prevents permanent lock deadlocks

**Mechanism:**
- 5-minute timeout (configurable)
- Automatic cleanup on lock attempt
- Manual cleanup available

**Limitations:**
- Time-based only (not process-based)
- Fixed timeout (may be too long or too short)
- No notification to lock holder

**Example:**

```bash
# Manual stale lock cleanup
claudeswarm cleanup-stale-locks

# Or with custom timeout (10 minutes)
python -c "
from claudeswarm.locking import LockManager
lm = LockManager()
count = lm.cleanup_stale_locks(timeout=600)
print(f'Cleaned {count} locks')
"
```

---

### 4. Atomic File Operations

**Protection:** Prevents file corruption from concurrent writes

**Mechanism:**
- Write to temporary file first
- Atomic rename operation
- File system guarantees atomicity

**Limitations:**
- Only protects the final write
- No transaction support
- No rollback mechanism

**Example:**

```python
import tempfile
from pathlib import Path

# Safe atomic write
def safe_write(filepath, content):
    tmp = tempfile.NamedTemporaryFile(
        mode='w',
        dir=filepath.parent,
        delete=False
    )
    try:
        tmp.write(content)
        tmp.close()
        Path(tmp.name).replace(filepath)
    except:
        Path(tmp.name).unlink()
        raise
```

---

## Known Limitations

### 1. No Authentication

**Issue:** Agents are identified only by self-declared IDs

**Risk:**
- Any agent can impersonate another
- No proof of identity
- Cannot verify sender of messages

**Mitigation:**
- Trust environment only
- Use in single-user scenarios
- Monitor for suspicious activity

**Future Enhancement:**
- Cryptographic signatures
- Agent certificates
- Challenge-response protocol

---

### 2. No Encryption

**Issue:** All data stored and transmitted in plain text

**Risk:**
- Messages visible in tmux history
- Lock files readable by all users
- Logs contain sensitive information

**Mitigation:**
- Use in trusted environments
- Restrict file permissions
- Clear sensitive data from logs

**File Permissions:**

```bash
# Restrict lock directory
chmod 700 .agent_locks/

# Restrict log files
chmod 600 agent_messages.log

# Restrict registry
chmod 600 ACTIVE_AGENTS.json
```

---

### 3. Lock Hijacking

**Issue:** Agents can release locks they don't own

**Risk:**
- Malicious agent releases other's locks
- Race conditions in lock release
- Accidental lock interference

**Mitigation:**
- Code review before deployment
- Monitor lock operations
- Use trusted agents only

**Lock Ownership Check:**

```python
from claudeswarm.locking import LockManager

lm = LockManager()

# Check before releasing
lock = lm.who_has_lock("file.py")
if lock and lock.agent_id == "my-agent":
    # Safe to release
    lm.release_lock("file.py", "my-agent")
else:
    print("Warning: Do not own this lock!")
```

---

### 4. Message Spoofing

**Issue:** No verification of message sender

**Risk:**
- False messages from fake agents
- Confusion in coordination
- Incorrect attribution

**Mitigation:**
- Trust environment
- Correlate with registry
- Verify sender before trusting

---

### 5. Denial of Service

**Issue:** Various DoS vectors exist

**Possible Attacks:**
- Message spam (mitigated by rate limiting)
- Lock spam (create many locks)
- Registry corruption
- Log file growth

**Mitigation:**
- Rate limiting enabled
- Regular cleanup (stale locks)
- Log rotation (automatic at 10MB)
- Monitor disk usage

---

## Best Practices

### 1. Principle of Least Privilege

**Always acquire minimal necessary locks:**

```python
# BAD: Overly broad lock
lm.acquire_lock("src/**/*.py", "agent-1", "refactoring")

# GOOD: Specific lock
lm.acquire_lock("src/auth/login.py", "agent-1", "refactoring login")
```

---

### 2. Always Release Locks

**Use try-finally or context managers:**

```python
# Pattern 1: try-finally
lm = LockManager()
success, conflict = lm.acquire_lock("file.py", "agent-1", "editing")

if success:
    try:
        # Do work
        edit_file("file.py")
    finally:
        # Always runs, even on exception
        lm.release_lock("file.py", "agent-1")
```

---

### 3. Validate Inputs

**Never trust user input in file paths:**

```python
from pathlib import Path

def safe_lock(user_path: str, agent_id: str):
    # Validate path
    path = Path(user_path).resolve()

    # Check it's within project
    project_root = Path.cwd()
    if not path.is_relative_to(project_root):
        raise ValueError("Path outside project root")

    # Check for path traversal
    if ".." in user_path:
        raise ValueError("Path traversal detected")

    # Now safe to use
    lm = LockManager()
    return lm.acquire_lock(str(path), agent_id, "safe operation")
```

---

### 4. Sanitize Log Data

**Don't log sensitive information:**

```python
from claudeswarm.messaging import send_message, MessageType

# BAD: Logs may contain secrets
send_message(
    sender_id="agent-1",
    recipient_id="agent-2",
    message_type=MessageType.INFO,
    content=f"Database password: {password}"  # DON'T DO THIS
)

# GOOD: Sanitize sensitive data
send_message(
    sender_id="agent-1",
    recipient_id="agent-2",
    message_type=MessageType.INFO,
    content="Database credentials updated successfully"
)
```

---

### 5. Regular Cleanup

**Schedule maintenance tasks:**

```bash
# Crontab entry for hourly cleanup
0 * * * * cd /path/to/project && claudeswarm cleanup-stale-locks

# Crontab for daily log rotation
0 0 * * * cd /path/to/project && gzip agent_messages.log.old

# Crontab for weekly old log deletion
0 0 * * 0 cd /path/to/project && find . -name "*.log.*.gz" -mtime +30 -delete
```

---

### 6. Monitor for Anomalies

**Watch for suspicious patterns:**

```python
from claudeswarm.discovery import list_active_agents
from claudeswarm.locking import LockManager

def check_security():
    """Basic security monitoring."""
    agents = list_active_agents()
    lm = LockManager()
    locks = lm.list_all_locks()

    # Check for too many agents
    if len(agents) > 10:
        print(f"WARNING: {len(agents)} agents active (expected <10)")

    # Check for long-held locks
    for lock in locks:
        age_minutes = lock.age_seconds() / 60
        if age_minutes > 30:
            print(f"WARNING: Lock on {lock.filepath} held for {age_minutes:.1f} minutes")

    # Check for stale locks
    stale = [l for l in locks if l.is_stale()]
    if stale:
        print(f"WARNING: {len(stale)} stale locks detected")

# Run periodically
check_security()
```

---

## Authentication

### Current State

**No authentication mechanism exists.** Agents are identified by self-declared string IDs.

### Recommended Approach for Trusted Environments

1. **Single User:**
   - Run all agents under same Unix user
   - File permissions enforce isolation

2. **Shared Workstation:**
   - Use group permissions
   - Trusted team members only

3. **Container/VM:**
   - Isolated environment per project
   - Network isolation

---

### Future Authentication Options

**If authentication is needed, consider:**

1. **Agent Certificates:**
   - Generate unique certificate per agent
   - Sign messages with private key
   - Verify signatures on receipt

2. **Session Tokens:**
   - Central authority issues tokens
   - Agents include token in messages
   - Tokens expire after session

3. **Challenge-Response:**
   - Prove identity before communication
   - Cryptographic challenge
   - Prevents impersonation

---

## Access Control

### File System Permissions

**Recommended permissions:**

```bash
# Project directory
chmod 750 .

# Lock directory (private)
chmod 700 .agent_locks/

# Registry (read-only for others)
chmod 644 ACTIVE_AGENTS.json

# Message log (private)
chmod 600 agent_messages.log

# Pending ACKs (private)
chmod 600 PENDING_ACKS.json
```

---

### tmux Access Control

**Secure tmux session:**

```bash
# Create session with specific socket
tmux -S /tmp/mysession-$(id -u) new -s myproject

# Set socket permissions
chmod 700 /tmp/mysession-$(id -u)

# Only your user can attach
tmux -S /tmp/mysession-$(id -u) attach
```

---

## Data Security

### Sensitive Data Handling

**Guidelines:**

1. **Never store credentials in:**
   - Lock files (visible to all agents)
   - Message log (persistent storage)
   - COORDINATION.md (shared file)
   - Agent messages (visible in tmux)

2. **Use environment variables:**

```python
import os

# Good: Load from environment
db_password = os.getenv("DATABASE_PASSWORD")

# Bad: Hard-code in messages
send_message(..., content=f"Password: {password}")  # DON'T
```

3. **Use separate secrets management:**
   - Hashicorp Vault
   - AWS Secrets Manager
   - Environment files with strict permissions

---

### Data Retention

**Configure retention policies:**

```bash
# Delete old logs after 30 days
find . -name "agent_messages.log.*.gz" -mtime +30 -delete

# Clean up old coordination snapshots
find . -name "COORDINATION.md.*" -mtime +7 -delete

# Archive and encrypt if needed
tar -czf archive-$(date +%Y%m).tar.gz *.log.old
gpg --encrypt archive-$(date +%Y%m).tar.gz
```

---

## Audit and Logging

### What is Logged

1. **Message Log (`agent_messages.log`):**
   - All message deliveries
   - Sender, recipients, timestamps
   - Delivery success/failure
   - Message content (sanitize sensitive data!)

2. **Lock Operations:**
   - Lock acquisitions (implicit in lock files)
   - Lock metadata (agent, reason, timestamp)

3. **Discovery:**
   - Agent registry updates
   - Agent status changes

---

### Log Monitoring

**Watch for security events:**

```bash
# Monitor for unusual activity
tail -f agent_messages.log | grep -E "(BLOCKED|ERROR|FAILED)"

# Count messages per agent
jq -r '.sender' agent_messages.log | sort | uniq -c | sort -rn

# Find long-running locks
find .agent_locks -name "*.lock" -mmin +60
```

---

### Log Analysis

**Periodic security review:**

```python
import json
from pathlib import Path
from collections import defaultdict

def analyze_logs():
    """Analyze message log for security issues."""
    log_file = Path("agent_messages.log")

    sender_counts = defaultdict(int)
    failed_deliveries = []

    with open(log_file) as f:
        for line in f:
            try:
                entry = json.loads(line)
                sender = entry.get('sender', 'unknown')
                sender_counts[sender] += 1

                if entry.get('failure_count', 0) > 0:
                    failed_deliveries.append(entry)
            except json.JSONDecodeError:
                continue

    # Report
    print(f"Message counts by sender:")
    for sender, count in sorted(sender_counts.items(), key=lambda x: x[1], reverse=True):
        print(f"  {sender}: {count}")

    print(f"\nFailed deliveries: {len(failed_deliveries)}")

analyze_logs()
```

---

## Incident Response

### Security Incident Types

1. **Compromised Agent:**
   - Agent behaving suspiciously
   - Unusual lock patterns
   - Message spam

2. **File Corruption:**
   - Registry corrupted
   - Lock files tampered with
   - Coordination file damaged

3. **System Compromise:**
   - Unauthorized access to project
   - Malicious code injection
   - Privilege escalation

---

### Response Procedures

**If suspicious activity detected:**

1. **Immediate Actions:**

```bash
# Stop all agents
tmux kill-server

# Backup current state
tar -czf incident-$(date +%Y%m%d-%H%M%S).tar.gz \
    ACTIVE_AGENTS.json agent_messages.log .agent_locks/

# Clean up
claudeswarm cleanup-stale-locks
rm -f ACTIVE_AGENTS.json
```

2. **Investigation:**
   - Review message logs
   - Check lock file timestamps
   - Verify agent identities
   - Review code changes

3. **Recovery:**
   - Reset to known good state
   - Rediscover agents
   - Resume operations
   - Monitor closely

---

### Forensics

**Preserve evidence:**

```bash
# Create forensic backup
timestamp=$(date +%Y%m%d-%H%M%S)
mkdir -p forensics/$timestamp

# Copy all state
cp -r .agent_locks/ forensics/$timestamp/
cp ACTIVE_AGENTS.json forensics/$timestamp/
cp agent_messages.log* forensics/$timestamp/
cp COORDINATION.md forensics/$timestamp/

# Hash for integrity
cd forensics/$timestamp
sha256sum * > checksums.txt

# Compress and protect
cd ..
tar -czf $timestamp.tar.gz $timestamp/
chmod 400 $timestamp.tar.gz
```

---

## Security Checklist

**Before deploying Claude Swarm:**

- [ ] Running in trusted environment only
- [ ] File permissions properly configured
- [ ] Rate limiting enabled
- [ ] Stale lock cleanup scheduled
- [ ] Log rotation configured
- [ ] No sensitive data in messages/logs
- [ ] Monitoring in place
- [ ] Backup strategy defined
- [ ] Incident response plan documented
- [ ] Team trained on security practices

**During operation:**

- [ ] Regular security reviews
- [ ] Monitor log files for anomalies
- [ ] Check for stale locks
- [ ] Verify agent count is expected
- [ ] Review lock durations
- [ ] Check disk space usage
- [ ] Rotate logs periodically

**After incidents:**

- [ ] Preserve forensic evidence
- [ ] Analyze root cause
- [ ] Update security procedures
- [ ] Retrain team if needed
- [ ] Document lessons learned

---

## Additional Resources

### Security Guidelines

- [OWASP Secure Coding Practices](https://owasp.org/www-project-secure-coding-practices-quick-reference-guide/)
- [CWE Top 25 Software Weaknesses](https://cwe.mitre.org/top25/)
- [NIST Cybersecurity Framework](https://www.nist.gov/cyberframework)

### File System Security

- [Linux File Permissions](https://linux.die.net/man/1/chmod)
- [Secure File Operations](https://docs.python.org/3/library/tempfile.html)

### Logging Best Practices

- [Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)

---

## Reporting Security Issues

If you discover a security vulnerability in Claude Swarm:

1. **Do not file a public issue**
2. Use GitHub's private vulnerability reporting:
   https://github.com/boriscardano/claude-swarm/security/advisories/new
3. Include:
   - Description of vulnerability
   - Steps to reproduce
   - Potential impact
   - Suggested mitigation

We aim to respond within 48 hours and issue a fix within 7 days for critical issues.

---

**Last Updated:** 2025-11-07

**Security Version:** 1.0

**Note:** This is a development tool for trusted environments. Do not use in production or untrusted scenarios without implementing additional security measures.
