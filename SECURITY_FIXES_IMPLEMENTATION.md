# Security Fixes Implementation Guide
**Quick reference for implementing the high-priority security recommendations**

---

## 🎯 Goal

Harden file permissions to prevent unauthorized access to lock files and message logs on shared systems.

**Time Required:** ~15 minutes
**Difficulty:** Easy
**Impact:** High security improvement

---

## 📋 Changes Summary

| File | Line | Change | Impact |
|------|------|--------|--------|
| `locking.py` | ~134 | Add `chmod(0o700)` to lock directory | Prevents other users from listing locks |
| `locking.py` | ~245 | Add `chmod(0o600)` to lock files | Prevents other users from reading lock metadata |
| `messaging.py` | ~422 | Add `chmod(0o600)` to message log | Prevents other users from reading message history |

---

## 🚀 Implementation Steps

### Step 1: Create Feature Branch

```bash
cd /Users/boris/work/aspire11/claude-swarm
git checkout -b security-file-permissions
```

### Step 2: Edit File 1 - locking.py

**Location:** `/Users/boris/work/aspire11/claude-swarm/src/claudeswarm/locking.py`

**Change A: Harden lock directory (line ~134)**

Find this method:
```python
def _ensure_lock_directory(self) -> None:
    """Create the lock directory if it doesn't exist."""
    self.lock_dir.mkdir(exist_ok=True, parents=True)
```

Change to:
```python
def _ensure_lock_directory(self) -> None:
    """Create the lock directory if it doesn't exist."""
    self.lock_dir.mkdir(exist_ok=True, parents=True)
    # Restrict access to owner only (prevent other users from listing locks)
    self.lock_dir.chmod(0o700)
```

**Change B: Harden lock files (line ~245)**

Find this method:
```python
def _write_lock(self, lock_path: Path, lock: FileLock) -> bool:
    """Write a lock to a file atomically.

    Uses exclusive file creation to ensure atomicity.

    Args:
        lock_path: Path to the lock file
        lock: FileLock object to write

    Returns:
        True if the lock was written successfully, False if file already exists
    """
    try:
        # Use 'x' mode for exclusive creation (fails if file exists)
        with lock_path.open("x") as f:
            json.dump(lock.to_dict(), f, indent=2)
        return True
    except FileExistsError:
        return False
    except OSError:
        return False
```

Change to:
```python
def _write_lock(self, lock_path: Path, lock: FileLock) -> bool:
    """Write a lock to a file atomically.

    Uses exclusive file creation to ensure atomicity.

    Args:
        lock_path: Path to the lock file
        lock: FileLock object to write

    Returns:
        True if the lock was written successfully, False if file already exists
    """
    try:
        # Use 'x' mode for exclusive creation (fails if file exists)
        with lock_path.open("x") as f:
            json.dump(lock.to_dict(), f, indent=2)
        # Restrict access to owner only (prevent other users from reading lock metadata)
        lock_path.chmod(0o600)
        return True
    except FileExistsError:
        return False
    except OSError:
        return False
```

### Step 3: Edit File 2 - messaging.py

**Location:** `/Users/boris/work/aspire11/claude-swarm/src/claudeswarm/messaging.py`

**Change: Harden message log (line ~422)**

Find this method:
```python
def __init__(self, log_file: Path = None):
    """Initialize message logger.

    Args:
        log_file: Path to log file (default: ./agent_messages.log)
    """
    self.log_file = log_file or Path("./agent_messages.log")
    self.max_size = 10 * 1024 * 1024  # 10MB

    # Create log file if it doesn't exist
    if not self.log_file.exists():
        self.log_file.touch()
```

Change to:
```python
def __init__(self, log_file: Path = None):
    """Initialize message logger.

    Args:
        log_file: Path to log file (default: ./agent_messages.log)
    """
    self.log_file = log_file or Path("./agent_messages.log")
    self.max_size = 10 * 1024 * 1024  # 10MB

    # Create log file if it doesn't exist
    if not self.log_file.exists():
        self.log_file.touch()
        # Restrict access to owner only (prevent other users from reading message history)
        self.log_file.chmod(0o600)
```

### Step 4: Verify Changes

```bash
# Check the diffs
git diff src/claudeswarm/locking.py
git diff src/claudeswarm/messaging.py

# Should show +3 lines added (one chmod per change location)
```

### Step 5: Test Changes

```bash
# Run the existing security tests
pytest tests/test_security.py -v

# Run all locking tests
pytest tests/test_locking.py -v

# Run all messaging tests
pytest tests/test_messaging.py -v

# Run integration tests
pytest tests/integration/ -v
```

**All tests should pass.** The changes only add permission hardening and don't affect functionality.

### Step 6: Create Manual Test

Create a test script to verify the permissions are correct:

```bash
# test-permissions.sh
#!/usr/bin/env bash

set -euo pipefail

echo "Testing file permission hardening..."

# Clean up any existing files
rm -rf .agent_locks agent_messages.log test_project

# Create test environment
mkdir -p test_project
cd test_project

# Test 1: Lock directory permissions
echo "Test 1: Creating lock directory..."
python3 -c "
import sys
sys.path.insert(0, '../src')
from claudeswarm.locking import LockManager
lm = LockManager()
"

# Check lock directory permissions
LOCK_DIR_PERMS=$(stat -f "%Sp" .agent_locks)
echo "Lock directory permissions: $LOCK_DIR_PERMS"
if [ "$LOCK_DIR_PERMS" != "drwx------" ]; then
    echo "❌ FAIL: Lock directory should be drwx------ (700), got $LOCK_DIR_PERMS"
    exit 1
fi
echo "✓ Lock directory permissions correct"

# Test 2: Lock file permissions
echo ""
echo "Test 2: Creating lock file..."
python3 -c "
import sys
sys.path.insert(0, '../src')
from claudeswarm.locking import LockManager
lm = LockManager()
lm.acquire_lock('test.py', 'agent-1', 'test')
"

# Check lock file permissions
LOCK_FILE=$(ls .agent_locks/*.lock | head -n 1)
LOCK_FILE_PERMS=$(stat -f "%Sp" "$LOCK_FILE")
echo "Lock file permissions: $LOCK_FILE_PERMS"
if [ "$LOCK_FILE_PERMS" != "-rw-------" ]; then
    echo "❌ FAIL: Lock file should be -rw------- (600), got $LOCK_FILE_PERMS"
    exit 1
fi
echo "✓ Lock file permissions correct"

# Test 3: Message log permissions
echo ""
echo "Test 3: Creating message log..."
python3 -c "
import sys
sys.path.insert(0, '../src')
from claudeswarm.messaging import MessageLogger
logger = MessageLogger()
"

# Check message log permissions
LOG_PERMS=$(stat -f "%Sp" agent_messages.log)
echo "Message log permissions: $LOG_PERMS"
if [ "$LOG_PERMS" != "-rw-------" ]; then
    echo "❌ FAIL: Message log should be -rw------- (600), got $LOG_PERMS"
    exit 1
fi
echo "✓ Message log permissions correct"

# Cleanup
cd ..
rm -rf test_project

echo ""
echo "✅ All permission tests passed!"
```

Run the test:
```bash
chmod +x test-permissions.sh
./test-permissions.sh
```

### Step 7: Harden Existing Files

Create a script to fix permissions on existing installations:

```bash
# scripts/harden-permissions.sh
#!/usr/bin/env bash
# Harden permissions on existing coordination files

set -euo pipefail

echo "Hardening permissions on existing Claude Swarm files..."
echo ""

# Function to safely change permissions
safe_chmod() {
    local perms=$1
    local path=$2

    if [ -e "$path" ]; then
        chmod "$perms" "$path"
        echo "✓ Set $perms on $path"
        return 0
    else
        echo "  (skipped - $path does not exist)"
        return 1
    fi
}

# Lock directory and files
if [ -d ".agent_locks" ]; then
    chmod 700 .agent_locks
    echo "✓ Set 700 on .agent_locks/"

    # Fix all lock files
    if ls .agent_locks/*.lock 1> /dev/null 2>&1; then
        chmod 600 .agent_locks/*.lock
        COUNT=$(ls .agent_locks/*.lock | wc -l)
        echo "✓ Set 600 on $COUNT lock file(s)"
    fi
fi

# Message log
safe_chmod 600 "agent_messages.log"
safe_chmod 600 "agent_messages.log.old"

# PENDING_ACKS
safe_chmod 600 "PENDING_ACKS.json"

# User's home directory secret
if [ -d "$HOME/.claude-swarm" ]; then
    chmod 700 "$HOME/.claude-swarm"
    echo "✓ Set 700 on ~/.claude-swarm/"

    if [ -f "$HOME/.claude-swarm/secret" ]; then
        chmod 600 "$HOME/.claude-swarm/secret"
        echo "✓ Set 600 on ~/.claude-swarm/secret"
    fi
fi

echo ""
echo "✅ Permission hardening complete!"
echo ""
echo "Summary of permission changes:"
echo "  drwx------  .agent_locks/          (700 - owner only)"
echo "  -rw-------  .agent_locks/*.lock    (600 - owner only)"
echo "  -rw-------  agent_messages.log     (600 - owner only)"
echo "  -rw-------  PENDING_ACKS.json      (600 - owner only)"
echo "  drwx------  ~/.claude-swarm/       (700 - owner only)"
echo "  -rw-------  ~/.claude-swarm/secret (600 - owner only)"
echo ""
echo "Note: ACTIVE_AGENTS.json remains 644 for discovery by other processes"
```

### Step 8: Add to Documentation

Update `docs/INTEGRATION_GUIDE.md` to include permission hardening step:

```markdown
## Post-Installation Security Hardening

After installing Claude Swarm, run the permission hardening script to secure coordination files:

\`\`\`bash
# In your project directory
bash <(curl -s https://raw.githubusercontent.com/borisbanach/claude-swarm/main/scripts/harden-permissions.sh)

# Or if you have the repo locally
./scripts/harden-permissions.sh
\`\`\`

This sets restrictive permissions on:
- Lock directory and files (700/600)
- Message logs (600)
- Pending ACKs (600)
- Secret file (600)

Run this script after installation and periodically to maintain security.
```

### Step 9: Commit Changes

```bash
# Stage the changes
git add src/claudeswarm/locking.py
git add src/claudeswarm/messaging.py
git add scripts/harden-permissions.sh
git add test-permissions.sh

# Commit with descriptive message
git commit -m "fix(security): harden file permissions for lock files and message logs

- Set lock directory to 0o700 (owner only)
- Set lock files to 0o600 (owner only)
- Set message log to 0o600 (owner only)
- Add permission hardening script for existing installations
- Add permission verification tests

Prevents unauthorized access to lock metadata and message history
on shared systems. Addresses high-priority security recommendations
from security review.

Issue: Security Review 2025-11-07
Severity: High
Impact: Improves security on multi-user systems"
```

### Step 10: Create Pull Request

```bash
# Push branch
git push origin security-file-permissions

# Create PR (if using gh CLI)
gh pr create \
  --title "Security: Harden file permissions for coordination files" \
  --body "## Summary

Implements high-priority security recommendations from the 2025-11-07 security review.

## Changes

- **locking.py**: Set lock directory to 0o700 and lock files to 0o600
- **messaging.py**: Set message log to 0o600 on creation
- **scripts/harden-permissions.sh**: Script to fix existing installations
- **test-permissions.sh**: Verification tests for permissions

## Testing

- ✅ All existing tests pass
- ✅ New permission tests pass
- ✅ Manual verification on test project

## Security Impact

**Before:**
- Lock files readable by all users (644)
- Message logs readable by all users (644)
- Other users could see agent coordination details

**After:**
- Lock files readable only by owner (600)
- Message logs readable only by owner (600)
- Coordination details private to user

## Deployment

For existing installations, users should run:
\`\`\`bash
./scripts/harden-permissions.sh
\`\`\`

New installations will automatically have hardened permissions.

## References

- Security Review Report: SECURITY_REVIEW_REPORT.md
- Security Summary: SECURITY_REVIEW_SUMMARY.md"
```

---

## 🧪 Testing Checklist

After implementing changes, verify:

- [ ] `pytest tests/test_security.py` passes
- [ ] `pytest tests/test_locking.py` passes
- [ ] `pytest tests/test_messaging.py` passes
- [ ] `./test-permissions.sh` passes
- [ ] Lock directory created with 700 permissions
- [ ] Lock files created with 600 permissions
- [ ] Message log created with 600 permissions
- [ ] Existing lock files can still be read/released
- [ ] Existing message log can still be written to
- [ ] No regression in agent discovery
- [ ] No regression in message delivery

---

## 🔍 Verification Commands

After deployment, verify the permissions:

```bash
# Check lock directory
stat -f "%Sp %N" .agent_locks
# Should show: drwx------ .agent_locks

# Check lock files
stat -f "%Sp %N" .agent_locks/*.lock
# Should show: -rw------- .agent_locks/xyz.lock

# Check message log
stat -f "%Sp %N" agent_messages.log
# Should show: -rw------- agent_messages.log

# Check secret
stat -f "%Sp %N" ~/.claude-swarm/secret
# Should show: -rw------- /Users/boris/.claude-swarm/secret
```

---

## 📝 Release Notes

**Version: v1.1.0 - Security Hardening Release**

### Security Improvements

- **High:** Lock files now created with restrictive permissions (600)
- **High:** Message logs now created with restrictive permissions (600)
- **High:** Lock directory now has restrictive permissions (700)
- **New:** Permission hardening script for existing installations
- **New:** Automated permission verification tests

### Migration Guide

**For existing users:**

1. Pull the latest version
2. Run `scripts/harden-permissions.sh` in your project directory
3. Verify with `ls -la .agent_locks/ agent_messages.log`

**No breaking changes.** All existing functionality preserved.

### Backwards Compatibility

✅ **Fully backwards compatible.** Existing lock files and logs continue to work.

The changes only affect:
- Newly created files (more restrictive permissions)
- Existing files can be hardened with the script

---

## 🎯 Success Criteria

Implementation is successful when:

1. ✅ All tests pass
2. ✅ New files have correct permissions (700/600)
3. ✅ No functionality regression
4. ✅ Documentation updated
5. ✅ Hardening script works on existing installations
6. ✅ Security review recommendations addressed

---

## 🚨 Rollback Plan

If issues arise:

```bash
# Revert the commits
git revert HEAD~3..HEAD

# Or reset to previous state
git reset --hard origin/main

# Fix permissions manually if needed
chmod 755 .agent_locks
chmod 644 .agent_locks/*.lock
chmod 644 agent_messages.log
```

---

## 📚 Additional Resources

- [Security Review Report](./SECURITY_REVIEW_REPORT.md) - Full analysis
- [Security Summary](./SECURITY_REVIEW_SUMMARY.md) - Quick reference
- [Security Documentation](./docs/security.md) - Guidelines
- [Integration Guide](./docs/INTEGRATION_GUIDE.md) - Setup instructions

---

**Implementation Guide Version:** 1.0
**Last Updated:** 2025-11-07
**Status:** Ready for implementation
