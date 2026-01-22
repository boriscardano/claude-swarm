# E2B Launcher Code Review Report

**File:** `/Users/boris/work/aspire11/claude-swarm/src/claudeswarm/cloud/e2b_launcher.py`
**Reviewer:** Claude Code Review Expert
**Date:** 2025-11-19
**Review Scope:** Production readiness for E2B Hackathon

---

## Executive Summary

The E2B launcher implementation demonstrates solid foundational architecture with good type safety and async patterns. However, there are **critical security and production readiness issues** that must be addressed before hackathon deployment. The code shows good structure and organization but lacks essential production features like logging, timeout management, and robust error recovery.

**Overall Grade:** C+ (Functional but needs hardening)

**Recommendation:** Address all CRITICAL and MAJOR issues before production deployment.

---

## 1. Security Assessment

### CRITICAL Issues

#### 🔴 SEC-1: Command Injection Vulnerability (Lines 116-120, 155-174, 197-204)
**Severity:** CRITICAL
**Impact:** Remote code execution risk

**Issue:**
Shell commands are constructed using string formatting with user-controlled input (`num_agents`). While `num_agents` is an integer in the constructor, there's no validation preventing negative numbers or extremely large values.

**Location:**
```python
# Line 155
'!tmux new-session -d -s claude-swarm -x 200 -y 50'

# Line 165
f'!tmux split-window -h -t claude-swarm'

# Line 198-199
cmd = (
    f"!tmux send-keys -t claude-swarm:{i} "
    f"'cd /workspace && claudeswarm discover-agents' Enter"
)
```

**Risk:**
If `num_agents` is manipulated (e.g., through API misuse or future code changes), it could lead to resource exhaustion or unexpected behavior.

**Fix:**
```python
def __init__(self, num_agents: int = 4) -> None:
    """Initialize a CloudSandbox."""
    if not isinstance(num_agents, int):
        raise TypeError(f"num_agents must be an integer, got {type(num_agents)}")
    if num_agents < 1 or num_agents > 100:
        raise ValueError(f"num_agents must be between 1 and 100, got {num_agents}")
    self.num_agents = num_agents
    self.sandbox: Optional[E2BSandbox] = None
    self.sandbox_id: Optional[str] = None
    self.mcp_bridge: Optional[MCPBridge] = None
```

---

#### 🔴 SEC-2: API Key Exposure in Error Messages (Lines 74-79)
**Severity:** CRITICAL
**Impact:** Credential leakage in logs/exceptions

**Issue:**
API key is retrieved but error messages could potentially expose it in stack traces if exception handling is added upstream.

**Location:**
```python
# Line 74
api_key = os.getenv("E2B_API_KEY")
if not api_key:
    raise RuntimeError(
        "E2B_API_KEY environment variable not set. "
        "Get your API key from https://e2b.dev/docs"
    )
```

**Risk:**
The variable `api_key` exists in the local scope. If future code logs exceptions with local variables, the key could be exposed.

**Fix:**
```python
# Verify API key is set without storing it
if not os.getenv("E2B_API_KEY"):
    raise RuntimeError(
        "E2B_API_KEY environment variable not set. "
        "Get your API key from https://e2b.dev/docs"
    )
# Let E2BSandbox retrieve it internally
self.sandbox = E2BSandbox()
```

---

#### 🔴 SEC-3: Hardcoded GitHub Repository URL (Line 119)
**Severity:** MAJOR
**Impact:** Supply chain attack vector

**Issue:**
The code installs from a hardcoded GitHub repository without version pinning or integrity verification.

**Location:**
```python
# Line 119
"pip install git+https://github.com/borisbanach/claude-swarm.git",
```

**Risk:**
- No version pinning (could pull malicious updates)
- No integrity verification (SHA/tag)
- Repository could be compromised
- Man-in-the-middle attacks possible

**Fix:**
```python
# Use version pinning with git tag or commit SHA
"pip install git+https://github.com/borisbanach/claude-swarm.git@v0.1.0",
# Or better, use a specific commit SHA for immutability
"pip install git+https://github.com/borisbanach/claude-swarm.git@<commit-sha>",
# Best practice: Use PyPI package with hash verification
"pip install --require-hashes claude-swarm==0.1.0 --hash sha256:...",
```

---

### MAJOR Security Issues

#### 🟠 SEC-4: Sandbox Isolation Not Verified (Lines 81-85)
**Severity:** MAJOR
**Impact:** Multi-tenant isolation concerns

**Issue:**
No verification that E2B sandbox is properly isolated. Multiple sandboxes could potentially interact.

**Fix:**
```python
# After sandbox creation, verify isolation
self.sandbox = E2BSandbox()
self.sandbox_id = self.sandbox.id

# Verify sandbox isolation (example check)
result = await asyncio.to_thread(
    self.sandbox.run_code,
    "!echo $HOSTNAME"
)
if not result or result.error:
    raise RuntimeError("Failed to verify sandbox isolation")

print(f"✓ Sandbox created with isolated environment: {self.sandbox_id}")
```

---

## 2. Error Handling & Resilience

### CRITICAL Issues

#### 🔴 ERR-1: No Timeout Protection (Lines 126-129, 153-174, 201-204)
**Severity:** CRITICAL
**Impact:** Indefinite hangs in production

**Issue:**
All `asyncio.to_thread()` calls lack timeout protection. A stuck command could hang forever.

**Location:**
```python
# Line 126-129 - No timeout
result = await asyncio.to_thread(
    self.sandbox.run_code,
    f"!{cmd}",
)
```

**Fix:**
```python
import asyncio

# Add timeout wrapper
async def _run_with_timeout(
    self, cmd: str, timeout: float = 300.0
) -> Any:
    """Run command with timeout protection."""
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(self.sandbox.run_code, cmd),
            timeout=timeout
        )
    except asyncio.TimeoutError as e:
        raise RuntimeError(
            f"Command timed out after {timeout}s: {cmd[:100]}"
        ) from e

# Use throughout the code
result = await self._run_with_timeout(f"!{cmd}", timeout=600.0)
```

---

#### 🔴 ERR-2: Partial Initialization Not Cleaned Up (Lines 87-94)
**Severity:** CRITICAL
**Impact:** Resource leaks on failure

**Issue:**
If `create()` fails partway through (e.g., after creating sandbox but during tmux setup), the sandbox is not cleaned up.

**Location:**
```python
# Lines 87-94
await self._install_dependencies()  # Could fail here
await self._setup_tmux()            # Or here
await self._initialize_swarm()      # Or here
```

**Fix:**
```python
async def create(self) -> str:
    """Create E2B sandbox with automatic cleanup on failure."""
    # ... validation code ...

    try:
        # Create sandbox
        print("🚀 Creating E2B sandbox...")
        self.sandbox = E2BSandbox()
        self.sandbox_id = self.sandbox.id
        print(f"✓ Sandbox created: {self.sandbox_id}")

        # Install dependencies
        await self._install_dependencies()

        # Setup tmux
        await self._setup_tmux()

        # Initialize claudeswarm
        await self._initialize_swarm()

        print(f"✓ Sandbox {self.sandbox_id} ready with {self.num_agents} agents")
        return self.sandbox_id

    except Exception as e:
        # Clean up partially initialized sandbox
        print(f"❌ Initialization failed: {e}")
        await self.cleanup()
        raise RuntimeError(f"Sandbox creation failed: {str(e)}") from e
```

---

### MAJOR Error Handling Issues

#### 🟠 ERR-3: Silent Failure in Swarm Initialization (Lines 205-206)
**Severity:** MAJOR
**Impact:** Agents may not initialize correctly

**Issue:**
Errors in agent initialization are logged as warnings but don't fail the operation.

**Location:**
```python
# Lines 205-206
if result.error:
    print(f"⚠️  Warning: Pane {i} initialization issue: {result.error}")
```

**Risk:**
System could appear to be "ready" but agents are not functional.

**Fix:**
```python
# Track failed initializations
failed_panes = []

for i in range(self.num_agents):
    cmd = (
        f"!tmux send-keys -t claude-swarm:{i} "
        f"'cd /workspace && claudeswarm discover-agents' Enter"
    )
    result = await asyncio.to_thread(
        self.sandbox.run_code,
        cmd,
    )
    if result.error:
        failed_panes.append(i)
        print(f"⚠️  Warning: Pane {i} initialization issue: {result.error}")

# Fail if too many agents failed
if len(failed_panes) > self.num_agents // 2:
    raise RuntimeError(
        f"Agent initialization failed for {len(failed_panes)}/{self.num_agents} agents. "
        f"Failed panes: {failed_panes}"
    )
elif failed_panes:
    print(f"⚠️  Warning: {len(failed_panes)} agents failed to initialize but continuing...")
```

---

#### 🟠 ERR-4: Magic Sleep Without Verification (Line 209)
**Severity:** MAJOR
**Impact:** Race conditions in production

**Issue:**
Fixed 3-second sleep assumes initialization completes, but provides no verification.

**Location:**
```python
# Line 209
await asyncio.sleep(3)
```

**Fix:**
```python
# Poll for agent readiness
async def _wait_for_agents(self, timeout: float = 30.0) -> None:
    """Wait for agents to become ready with polling."""
    start_time = asyncio.get_event_loop().time()

    while True:
        # Check if agents are responding
        result = await asyncio.to_thread(
            self.sandbox.run_code,
            "!tmux list-panes -t claude-swarm -F '#{pane_id}'"
        )

        if not result.error and result.text:
            # Panes are active
            break

        elapsed = asyncio.get_event_loop().time() - start_time
        if elapsed > timeout:
            raise RuntimeError(f"Agents failed to initialize within {timeout}s")

        await asyncio.sleep(1)

    print("✓ All agents are responsive")

# Replace sleep with verification
await self._wait_for_agents(timeout=30.0)
```

---

## 3. Performance & Resource Management

### MAJOR Issues

#### 🟠 PERF-1: No Connection Pooling for HTTP Client (Lines 313-314 in mcp_bridge.py)
**Severity:** MAJOR
**Impact:** Connection exhaustion under load

**Issue:**
While not in e2b_launcher.py directly, the MCPBridge creates HTTP clients on-demand without pooling.

**Fix:** Already properly handled in MCPBridge with context manager pattern, but ensure it's used:
```python
async def attach_mcp(self, mcp_type: str, config: MCPConfig) -> MCPContainerInfo:
    """Attach MCP server to sandbox."""
    if not self.sandbox_id:
        raise RuntimeError("Sandbox must be created before attaching MCPs")

    # Create MCP bridge with context manager if not already created
    if self.mcp_bridge is None:
        self.mcp_bridge = MCPBridge(sandbox_id=self.sandbox_id)
        # Initialize HTTP client
        await self.mcp_bridge.__aenter__()
```

---

#### 🟠 PERF-2: Sequential Command Execution (Lines 123-135)
**Severity:** MINOR
**Impact:** Slow initialization

**Issue:**
Dependencies are installed sequentially. Could be parallelized where safe.

**Fix:**
```python
async def _install_dependencies(self) -> None:
    """Install required packages in parallel where possible."""
    print("📦 Installing dependencies...")

    # System packages (must be sequential)
    system_cmd = "apt-get update && apt-get install -y tmux git"
    result = await self._run_with_timeout(f"!{system_cmd}", timeout=600)
    if result.error:
        raise RuntimeError(f"Failed to install system packages: {result.error}")

    # Python packages can be installed in parallel
    python_cmds = [
        "pip install --upgrade pip",
        "pip install git+https://github.com/borisbanach/claude-swarm.git@v0.1.0",
        "pip install fastapi uvicorn pytest",
    ]

    # Run Python installations in parallel
    tasks = [
        self._run_with_timeout(f"!{cmd}", timeout=600)
        for cmd in python_cmds
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    for i, result in enumerate(results):
        if isinstance(result, Exception):
            raise RuntimeError(
                f"Failed to install Python package: {python_cmds[i]}"
            ) from result
        if result.error:
            raise RuntimeError(
                f"Failed to install Python package: {result.error}"
            )

    print("✓ Dependencies installed")
```

---

#### 🟡 PERF-3: No Resource Limits (Lines 38-48)
**Severity:** MINOR
**Impact:** Potential resource exhaustion

**Issue:**
No limits on sandbox resources (CPU, memory, disk).

**Fix:**
```python
class CloudSandbox:
    """Manages a single E2B sandbox with resource limits."""

    # Class constants for resource limits
    MAX_AGENTS = 100
    MIN_AGENTS = 1
    DEFAULT_TIMEOUT = 7200  # 2 hours
    MAX_SANDBOX_LIFETIME = 28800  # 8 hours

    def __init__(
        self,
        num_agents: int = 4,
        timeout: float = DEFAULT_TIMEOUT,
        max_memory_mb: Optional[int] = None,
    ) -> None:
        """Initialize with resource limits."""
        if num_agents < self.MIN_AGENTS or num_agents > self.MAX_AGENTS:
            raise ValueError(
                f"num_agents must be between {self.MIN_AGENTS} and {self.MAX_AGENTS}"
            )

        self.num_agents = num_agents
        self.timeout = min(timeout, self.MAX_SANDBOX_LIFETIME)
        self.max_memory_mb = max_memory_mb
        # ... rest of init
```

---

## 4. Code Quality & Maintainability

### Positive Aspects ✅

1. **Excellent Type Hints** (Throughout)
   - All methods have proper type annotations
   - Optional types used correctly
   - Return types specified

2. **Comprehensive Docstrings** (Lines 21-36, 50-66, etc.)
   - Class and method documentation is thorough
   - Includes examples for complex methods
   - Documents raises clauses

3. **Good Separation of Concerns** (Lines 99-214)
   - Private methods for each initialization step
   - Clear single responsibility per method
   - Good method naming conventions

4. **Context Manager Support** (Lines 322-329)
   - Proper async context manager implementation
   - Automatic cleanup on exit
   - Follows Python best practices

---

### MAJOR Code Quality Issues

#### 🟠 QA-1: No Structured Logging (Throughout)
**Severity:** MAJOR
**Impact:** Production debugging impossible

**Issue:**
Using `print()` statements instead of structured logging. No log levels, no timestamps, no correlation IDs.

**Location:**
```python
# Lines 82, 85, 96, 112, 137, etc.
print("🚀 Creating E2B sandbox...")
print(f"✓ Sandbox created: {self.sandbox_id}")
```

**Fix:**
```python
import logging
from typing import Optional

class CloudSandbox:
    """Manages a single E2B sandbox."""

    def __init__(self, num_agents: int = 4) -> None:
        """Initialize a CloudSandbox."""
        # Validation...

        # Set up structured logging
        self.logger = logging.getLogger(f"cloudsandbox.{id(self)}")
        self.logger.setLevel(logging.INFO)

        # Add context to all logs
        self.log_context = {
            "component": "cloud_sandbox",
            "num_agents": num_agents,
        }

    def _log(
        self,
        level: int,
        message: str,
        **kwargs: Any
    ) -> None:
        """Log with context."""
        context = {**self.log_context, **kwargs}
        extra = {"context": context}
        self.logger.log(level, message, extra=extra)

    async def create(self) -> str:
        """Create E2B sandbox."""
        self._log(logging.INFO, "Creating E2B sandbox")

        self.sandbox = E2BSandbox()
        self.sandbox_id = self.sandbox.id

        # Update context
        self.log_context["sandbox_id"] = self.sandbox_id

        self._log(
            logging.INFO,
            "Sandbox created successfully",
            sandbox_id=self.sandbox_id
        )

        # ... rest of method
```

---

#### 🟠 QA-2: No Metrics/Observability Hooks (Throughout)
**Severity:** MAJOR
**Impact:** Cannot monitor production health

**Issue:**
No hooks for monitoring initialization time, failure rates, resource usage.

**Fix:**
```python
from dataclasses import dataclass
from time import time
from typing import Optional

@dataclass
class SandboxMetrics:
    """Metrics for sandbox operations."""

    creation_time: float = 0.0
    dependency_install_time: float = 0.0
    tmux_setup_time: float = 0.0
    swarm_init_time: float = 0.0
    total_init_time: float = 0.0
    commands_executed: int = 0
    commands_failed: int = 0

class CloudSandbox:
    def __init__(self, num_agents: int = 4) -> None:
        """Initialize with metrics tracking."""
        # ... existing code ...
        self.metrics = SandboxMetrics()
        self._start_time: Optional[float] = None

    async def create(self) -> str:
        """Create E2B sandbox with metrics."""
        self._start_time = time()

        try:
            # Create sandbox
            step_start = time()
            self.sandbox = E2BSandbox()
            self.sandbox_id = self.sandbox.id
            self.metrics.creation_time = time() - step_start

            # Install dependencies
            step_start = time()
            await self._install_dependencies()
            self.metrics.dependency_install_time = time() - step_start

            # Setup tmux
            step_start = time()
            await self._setup_tmux()
            self.metrics.tmux_setup_time = time() - step_start

            # Initialize swarm
            step_start = time()
            await self._initialize_swarm()
            self.metrics.swarm_init_time = time() - step_start

            self.metrics.total_init_time = time() - self._start_time

            self._log(
                logging.INFO,
                "Sandbox initialization complete",
                metrics=self.metrics.__dict__
            )

            return self.sandbox_id

        except Exception as e:
            self.metrics.total_init_time = time() - (self._start_time or time())
            self._log(
                logging.ERROR,
                "Sandbox initialization failed",
                error=str(e),
                metrics=self.metrics.__dict__
            )
            raise

    def get_metrics(self) -> SandboxMetrics:
        """Get current metrics."""
        return self.metrics
```

---

### MINOR Code Quality Issues

#### 🟡 QA-3: Type Ignore Comments Without Explanation (Lines 15, 127, 154, etc.)
**Severity:** MINOR
**Impact:** Reduced type safety

**Location:**
```python
# Line 15
E2BSandbox = None  # type: ignore[assignment, misc]

# Line 127
self.sandbox.run_code,  # type: ignore[union-attr]
```

**Fix:**
```python
# Add explanatory comments
E2BSandbox = None  # type: ignore[assignment, misc] - Optional dependency, loaded at runtime

# Or better, use proper conditional imports
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from e2b_code_interpreter import Sandbox as E2BSandbox
else:
    try:
        from e2b_code_interpreter import Sandbox as E2BSandbox
    except ImportError:
        E2BSandbox = None  # type: ignore[assignment]
```

---

#### 🟡 QA-4: Inconsistent Error Message Formatting (Throughout)
**Severity:** MINOR
**Impact:** Reduced user experience

**Fix:**
```python
# Create standardized error messages
class CloudSandboxError(Exception):
    """Base exception for CloudSandbox operations."""

    def __init__(
        self,
        message: str,
        sandbox_id: Optional[str] = None,
        step: Optional[str] = None,
        original_error: Optional[Exception] = None
    ):
        self.message = message
        self.sandbox_id = sandbox_id
        self.step = step
        self.original_error = original_error
        super().__init__(self._format_message())

    def _format_message(self) -> str:
        parts = [f"CloudSandbox Error: {self.message}"]
        if self.sandbox_id:
            parts.append(f"Sandbox: {self.sandbox_id}")
        if self.step:
            parts.append(f"Step: {self.step}")
        if self.original_error:
            parts.append(f"Cause: {str(self.original_error)}")
        return " | ".join(parts)

# Use throughout
raise CloudSandboxError(
    message="Failed to install dependencies",
    sandbox_id=self.sandbox_id,
    step="dependency_installation",
    original_error=e
)
```

---

## 5. Production Readiness

### CRITICAL Production Issues

#### 🔴 PROD-1: No Health Check Endpoint (Missing)
**Severity:** CRITICAL
**Impact:** Cannot verify sandbox is operational

**Fix:**
```python
async def health_check(self) -> dict[str, Any]:
    """Check sandbox health and agent status."""
    if not self.sandbox or not self.sandbox_id:
        return {
            "status": "unhealthy",
            "reason": "Sandbox not initialized",
        }

    try:
        # Check sandbox is responsive
        result = await asyncio.wait_for(
            asyncio.to_thread(
                self.sandbox.run_code,
                "!echo 'health_check'"
            ),
            timeout=5.0
        )

        if result.error:
            return {
                "status": "unhealthy",
                "reason": f"Sandbox unresponsive: {result.error}",
                "sandbox_id": self.sandbox_id,
            }

        # Check tmux session exists
        result = await asyncio.wait_for(
            asyncio.to_thread(
                self.sandbox.run_code,
                "!tmux has-session -t claude-swarm"
            ),
            timeout=5.0
        )

        if result.error:
            return {
                "status": "degraded",
                "reason": "Tmux session not found",
                "sandbox_id": self.sandbox_id,
            }

        return {
            "status": "healthy",
            "sandbox_id": self.sandbox_id,
            "num_agents": self.num_agents,
            "uptime": time() - (self._start_time or 0),
            "metrics": self.metrics.__dict__ if hasattr(self, 'metrics') else {},
        }

    except asyncio.TimeoutError:
        return {
            "status": "unhealthy",
            "reason": "Health check timed out",
            "sandbox_id": self.sandbox_id,
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "reason": f"Health check failed: {str(e)}",
            "sandbox_id": self.sandbox_id,
        }
```

---

#### 🔴 PROD-2: No Graceful Shutdown (Lines 304-320)
**Severity:** CRITICAL
**Impact:** Data loss and resource leaks

**Issue:**
Cleanup is abrupt. No graceful shutdown of agents.

**Fix:**
```python
async def cleanup(self, timeout: float = 30.0) -> None:
    """
    Gracefully shutdown sandbox and cleanup resources.

    Args:
        timeout: Maximum time to wait for graceful shutdown
    """
    shutdown_start = time()

    try:
        # Signal agents to shutdown gracefully
        if self.sandbox:
            self._log(logging.INFO, "Initiating graceful shutdown")

            # Send shutdown signal to all panes
            for i in range(self.num_agents):
                try:
                    await asyncio.wait_for(
                        asyncio.to_thread(
                            self.sandbox.run_code,
                            f"!tmux send-keys -t claude-swarm:{i} C-c"
                        ),
                        timeout=5.0
                    )
                except asyncio.TimeoutError:
                    self._log(
                        logging.WARNING,
                        f"Agent {i} did not respond to shutdown signal"
                    )

            # Wait for graceful shutdown
            await asyncio.sleep(2)

        # Cleanup MCP containers
        if self.mcp_bridge:
            self._log(logging.INFO, "Cleaning up MCP containers")
            await self.mcp_bridge.cleanup()

        # Close sandbox
        if self.sandbox:
            self._log(logging.INFO, f"Closing sandbox {self.sandbox_id}")

            remaining_time = timeout - (time() - shutdown_start)
            if remaining_time > 0:
                await asyncio.wait_for(
                    asyncio.to_thread(self.sandbox.close),
                    timeout=remaining_time
                )
            else:
                # Force close if timeout exceeded
                await asyncio.to_thread(self.sandbox.close)

            self._log(logging.INFO, "Sandbox closed successfully")

    except asyncio.TimeoutError:
        self._log(
            logging.ERROR,
            f"Graceful shutdown timed out after {timeout}s, forcing cleanup"
        )
        # Force cleanup
        if self.sandbox:
            try:
                await asyncio.to_thread(self.sandbox.close)
            except Exception as e:
                self._log(logging.ERROR, f"Force cleanup failed: {e}")

    except Exception as e:
        self._log(logging.ERROR, f"Cleanup error: {e}")
        raise
    finally:
        # Record cleanup metrics
        if hasattr(self, 'metrics'):
            self.metrics.total_init_time = time() - (self._start_time or 0)
```

---

#### 🔴 PROD-3: No Rate Limiting on Sandbox Creation (Missing)
**Severity:** MAJOR
**Impact:** API quota exhaustion

**Fix:**
```python
# Module-level rate limiting
from collections import deque
from threading import Lock

_sandbox_creation_timestamps: deque[float] = deque(maxlen=100)
_sandbox_creation_lock = Lock()

# Constants
MAX_SANDBOXES_PER_HOUR = 50
MAX_SANDBOXES_PER_MINUTE = 10

def _check_creation_rate_limit() -> None:
    """Check if we can create a new sandbox without exceeding rate limits."""
    now = time()

    with _sandbox_creation_lock:
        # Remove timestamps older than 1 hour
        while _sandbox_creation_timestamps and \
              _sandbox_creation_timestamps[0] < now - 3600:
            _sandbox_creation_timestamps.popleft()

        # Check hourly limit
        if len(_sandbox_creation_timestamps) >= MAX_SANDBOXES_PER_HOUR:
            raise RuntimeError(
                f"Rate limit exceeded: {MAX_SANDBOXES_PER_HOUR} sandboxes/hour. "
                f"Try again in {int(3600 - (now - _sandbox_creation_timestamps[0]))}s"
            )

        # Check per-minute limit
        recent = [ts for ts in _sandbox_creation_timestamps if ts > now - 60]
        if len(recent) >= MAX_SANDBOXES_PER_MINUTE:
            raise RuntimeError(
                f"Rate limit exceeded: {MAX_SANDBOXES_PER_MINUTE} sandboxes/minute. "
                f"Try again in {int(60 - (now - recent[0]))}s"
            )

        # Record this creation
        _sandbox_creation_timestamps.append(now)

# Use in create method
async def create(self) -> str:
    """Create E2B sandbox with rate limiting."""
    _check_creation_rate_limit()

    # ... rest of creation logic
```

---

## 6. Edge Cases & Integration

### MAJOR Edge Case Issues

#### 🟠 EDGE-1: No Handling of Sandbox Quota Exhaustion (Line 83)
**Severity:** MAJOR
**Impact:** Unclear errors when quota exceeded

**Fix:**
```python
try:
    self.sandbox = E2BSandbox()
    self.sandbox_id = self.sandbox.id
except Exception as e:
    error_msg = str(e).lower()

    # Check for quota-related errors
    if any(keyword in error_msg for keyword in ['quota', 'limit', 'exceeded', 'throttle']):
        raise RuntimeError(
            "E2B sandbox quota exceeded. "
            "Check your E2B dashboard at https://e2b.dev/dashboard "
            "for usage limits and upgrade options."
        ) from e

    # Check for authentication errors
    if any(keyword in error_msg for keyword in ['auth', 'unauthorized', 'forbidden', 'invalid key']):
        raise RuntimeError(
            "E2B authentication failed. "
            "Verify your E2B_API_KEY is correct and active."
        ) from e

    # Generic error
    raise RuntimeError(
        f"Failed to create E2B sandbox: {str(e)}"
    ) from e
```

---

#### 🟠 EDGE-2: Tmux Session Name Collision (Line 155)
**Severity:** MAJOR
**Impact:** Multiple sandboxes could conflict

**Issue:**
All sandboxes use the same tmux session name "claude-swarm".

**Fix:**
```python
async def _setup_tmux(self) -> None:
    """Create tmux session with unique name."""
    # Use sandbox_id in session name to prevent collisions
    session_name = f"claude-swarm-{self.sandbox_id}"

    print(f"🖥️  Setting up tmux with {self.num_agents} panes...")

    try:
        # Create initial session with unique name
        result = await self._run_with_timeout(
            f'!tmux new-session -d -s {session_name} -x 200 -y 50',
            timeout=10.0
        )
        if result.error:
            raise RuntimeError(f"Failed to create tmux session: {result.error}")

        # Split into multiple panes
        for i in range(1, self.num_agents):
            result = await self._run_with_timeout(
                f'!tmux split-window -h -t {session_name}',
                timeout=10.0
            )
            if result.error:
                raise RuntimeError(f"Failed to split pane {i}: {result.error}")

            await asyncio.to_thread(
                self.sandbox.run_code,
                f'!tmux select-layout -t {session_name} tiled',
            )

        # Store session name for later use
        self._tmux_session = session_name
        print("✓ Tmux session created")

    except Exception as e:
        raise RuntimeError(f"Tmux setup failed: {str(e)}") from e

# Update _initialize_swarm to use stored session name
async def _initialize_swarm(self) -> None:
    """Initialize claudeswarm in each pane."""
    session_name = getattr(self, '_tmux_session', 'claude-swarm')

    # ... use session_name instead of hardcoded 'claude-swarm'
```

---

#### 🟡 EDGE-3: No Handling of Network Interruptions (Throughout)
**Severity:** MINOR
**Impact:** Poor user experience on network issues

**Fix:**
```python
from httpx import NetworkError, TimeoutException

async def _run_with_retry(
    self,
    operation: str,
    func: Callable[[], Awaitable[Any]],
    max_retries: int = 3,
    backoff_base: float = 2.0,
) -> Any:
    """Run operation with exponential backoff retry on network errors."""
    last_error: Optional[Exception] = None

    for attempt in range(max_retries):
        try:
            return await func()
        except (NetworkError, TimeoutException, OSError) as e:
            last_error = e

            if attempt < max_retries - 1:
                wait_time = backoff_base ** attempt
                self._log(
                    logging.WARNING,
                    f"{operation} failed (attempt {attempt + 1}/{max_retries}), "
                    f"retrying in {wait_time}s",
                    error=str(e)
                )
                await asyncio.sleep(wait_time)
            else:
                self._log(
                    logging.ERROR,
                    f"{operation} failed after {max_retries} attempts",
                    error=str(e)
                )

    raise RuntimeError(
        f"{operation} failed after {max_retries} retries: {str(last_error)}"
    ) from last_error
```

---

## 7. Testing & Testability

### Positive Testing Aspects ✅

1. **Good Test Coverage Structure** (test_cloud_e2b_launcher.py)
   - Unit tests with mocking
   - Integration tests marked separately
   - Context manager testing

2. **Proper Mock Usage** (Lines 44-76 in tests)
   - AsyncMock for async operations
   - Proper patching of E2B SDK

---

### MAJOR Testing Issues

#### 🟠 TEST-1: No Integration Test for MCP Bridge (Missing)
**Severity:** MAJOR
**Impact:** Integration bugs may not be caught

**Fix:**
```python
@pytest.mark.asyncio
async def test_attach_mcp_integration(self) -> None:
    """Test MCP attachment integration."""
    from claudeswarm.cloud.types import MCPConfig, MCPType

    mock_sandbox = MagicMock()
    mock_sandbox.id = "test-sandbox-123"

    sandbox = CloudSandbox(num_agents=2)
    sandbox.sandbox = mock_sandbox
    sandbox.sandbox_id = "test-sandbox-123"

    # Create MCP config
    config = MCPConfig(
        mcp_type=MCPType.GITHUB,
        container_image="mcp/github:latest",
        environment={"GITHUB_TOKEN": "test-token"}
    )

    # Test attachment
    with patch("claudeswarm.cloud.mcp_bridge.MCPBridge") as mock_bridge_class:
        mock_bridge = MagicMock()
        mock_bridge.attach_mcp = AsyncMock(
            return_value=MagicMock(endpoint_url="http://localhost:3000")
        )
        mock_bridge_class.return_value = mock_bridge

        container_info = await sandbox.attach_mcp(
            mcp_type=MCPType.GITHUB,
            config=config
        )

        # Verify bridge was created
        assert sandbox.mcp_bridge is not None

        # Verify attach_mcp was called
        mock_bridge.attach_mcp.assert_called_once_with(
            mcp_type=MCPType.GITHUB,
            config=config
        )
```

---

#### 🟠 TEST-2: No Timeout Tests (Missing)
**Severity:** MAJOR
**Impact:** Timeout behavior not verified

**Fix:**
```python
@pytest.mark.asyncio
async def test_install_dependencies_timeout(self) -> None:
    """Test _install_dependencies handles timeouts."""
    mock_sandbox = MagicMock()
    mock_sandbox.id = "test-sandbox-123"

    # Mock a hanging operation
    async def hanging_operation(*args, **kwargs):
        await asyncio.sleep(1000)  # Never completes

    with patch("asyncio.to_thread", side_effect=hanging_operation):
        sandbox = CloudSandbox(num_agents=4)
        sandbox.sandbox = mock_sandbox

        # Should timeout and raise error
        with pytest.raises(RuntimeError, match="timed out"):
            await sandbox._install_dependencies()
```

---

## 8. Documentation & Examples

### Positive Documentation Aspects ✅

1. **Comprehensive Module Docstring** (Lines 1-6)
2. **Method Examples** (Lines 236-249, 271-282)
3. **Clear Attribute Documentation** (Lines 32-36)

---

### MINOR Documentation Issues

#### 🟡 DOC-1: Missing Cleanup Behavior in Docstring (Line 305)
**Severity:** MINOR

**Fix:**
```python
async def cleanup(self) -> None:
    """
    Shutdown sandbox and cleanup resources.

    This method performs the following cleanup operations:
    1. Sends shutdown signal to all agent panes
    2. Stops and removes all MCP containers
    3. Closes the E2B sandbox connection
    4. Releases all resources

    The cleanup is idempotent and safe to call multiple times.

    Note:
        This method is automatically called when using the async context manager.
        Manual calls are only needed when not using the context manager.

    Raises:
        Exception: If cleanup fails critically, though most errors are logged
                  and suppressed to ensure best-effort cleanup.

    Example:
        ```python
        sandbox = CloudSandbox(num_agents=4)
        await sandbox.create()
        try:
            # Use sandbox...
            pass
        finally:
            await sandbox.cleanup()  # Ensure cleanup even on errors
        ```
    """
```

---

## 9. Summary of Issues by Severity

### CRITICAL (Must Fix Before Production)
1. **SEC-1:** Command injection validation missing
2. **SEC-2:** API key exposure risk
3. **SEC-3:** Hardcoded unversioned git dependency
4. **ERR-1:** No timeout protection on async operations
5. **ERR-2:** Partial initialization not cleaned up
6. **PROD-1:** No health check endpoint
7. **PROD-2:** No graceful shutdown

### MAJOR (Should Fix Before Hackathon)
1. **SEC-4:** Sandbox isolation not verified
2. **ERR-3:** Silent failures in agent initialization
3. **ERR-4:** Magic sleep without verification
4. **QA-1:** No structured logging
5. **QA-2:** No metrics/observability hooks
6. **PROD-3:** No rate limiting on sandbox creation
7. **EDGE-1:** No handling of quota exhaustion
8. **EDGE-2:** Tmux session name collision
9. **TEST-1:** Missing MCP integration tests
10. **TEST-2:** No timeout tests

### MINOR (Nice to Have)
1. **PERF-2:** Sequential dependency installation
2. **PERF-3:** No resource limits
3. **QA-3:** Type ignore without explanation
4. **QA-4:** Inconsistent error formatting
5. **EDGE-3:** No network interruption handling
6. **DOC-1:** Missing cleanup behavior docs

---

## 10. Positive Highlights

### What's Done Well ✅

1. **Type Safety:** Excellent use of type hints throughout
2. **Async Patterns:** Proper async/await usage
3. **Context Managers:** Good resource management pattern
4. **Separation of Concerns:** Clean method organization
5. **Documentation:** Comprehensive docstrings with examples
6. **Test Structure:** Well-organized test suite with mocking
7. **Error Messages:** Helpful error messages with actionable guidance
8. **MCPBridge Integration:** Clean separation of MCP concerns

---

## 11. Recommended Action Plan

### Phase 1: Pre-Hackathon (Critical)
**Timeline: Immediate (1-2 days)**

1. Add input validation to `__init__` (SEC-1)
2. Remove API key from local scope (SEC-2)
3. Pin git dependency version (SEC-3)
4. Add timeout wrapper for all async operations (ERR-1)
5. Add try/except with cleanup in `create()` (ERR-2)
6. Implement basic health check (PROD-1)
7. Add structured logging (QA-1)

### Phase 2: Hackathon Hardening (Major)
**Timeline: 2-3 days**

1. Verify sandbox isolation (SEC-4)
2. Fix silent failures in agent init (ERR-3)
3. Replace sleep with polling (ERR-4)
4. Add metrics collection (QA-2)
5. Implement graceful shutdown (PROD-2)
6. Add rate limiting (PROD-3)
7. Handle quota exhaustion (EDGE-1)
8. Fix tmux session collision (EDGE-2)

### Phase 3: Post-Hackathon Improvements (Minor)
**Timeline: Ongoing**

1. Parallelize dependency installation (PERF-2)
2. Add resource limits (PERF-3)
3. Add network retry logic (EDGE-3)
4. Complete test coverage (TEST-1, TEST-2)
5. Improve documentation (DOC-1)

---

## 12. Code Examples for Priority Fixes

### Example 1: Complete Hardened `create()` Method

```python
async def create(self) -> str:
    """
    Create E2B sandbox and initialize environment with full error handling.

    Returns:
        str: The sandbox ID

    Raises:
        CloudSandboxError: If creation fails at any step
    """
    if E2BSandbox is None:
        raise CloudSandboxError(
            message="e2b-code-interpreter package not installed. "
                   "Install with: pip install e2b-code-interpreter",
            step="package_check"
        )

    # Verify API key without storing it
    if not os.getenv("E2B_API_KEY"):
        raise CloudSandboxError(
            message="E2B_API_KEY environment variable not set. "
                   "Get your API key from https://e2b.dev/docs",
            step="api_key_check"
        )

    # Check rate limits
    _check_creation_rate_limit()

    self._start_time = time()
    step_times: dict[str, float] = {}

    try:
        # Create sandbox with quota handling
        self._log(logging.INFO, "Creating E2B sandbox")
        step_start = time()

        try:
            self.sandbox = E2BSandbox()
            self.sandbox_id = self.sandbox.id
        except Exception as e:
            error_msg = str(e).lower()
            if any(kw in error_msg for kw in ['quota', 'limit', 'exceeded']):
                raise CloudSandboxError(
                    message="E2B quota exceeded. Check dashboard for limits.",
                    step="sandbox_creation",
                    original_error=e
                )
            if any(kw in error_msg for kw in ['auth', 'unauthorized']):
                raise CloudSandboxError(
                    message="E2B authentication failed. Verify API key.",
                    step="sandbox_creation",
                    original_error=e
                )
            raise CloudSandboxError(
                message=f"Sandbox creation failed: {str(e)}",
                step="sandbox_creation",
                original_error=e
            )

        step_times["sandbox_creation"] = time() - step_start
        self.log_context["sandbox_id"] = self.sandbox_id
        self._log(
            logging.INFO,
            "Sandbox created successfully",
            duration_ms=(step_times["sandbox_creation"] * 1000)
        )

        # Install dependencies with timeout
        step_start = time()
        await self._install_dependencies()
        step_times["dependency_installation"] = time() - step_start
        self._log(
            logging.INFO,
            "Dependencies installed",
            duration_ms=(step_times["dependency_installation"] * 1000)
        )

        # Setup tmux with unique session name
        step_start = time()
        await self._setup_tmux()
        step_times["tmux_setup"] = time() - step_start
        self._log(
            logging.INFO,
            "Tmux session configured",
            duration_ms=(step_times["tmux_setup"] * 1000)
        )

        # Initialize agents with verification
        step_start = time()
        await self._initialize_swarm()
        step_times["swarm_initialization"] = time() - step_start
        self._log(
            logging.INFO,
            "Swarm initialized",
            duration_ms=(step_times["swarm_initialization"] * 1000)
        )

        # Verify health
        health = await self.health_check()
        if health["status"] != "healthy":
            raise CloudSandboxError(
                message=f"Sandbox unhealthy after initialization: {health.get('reason')}",
                sandbox_id=self.sandbox_id,
                step="health_check"
            )

        total_time = time() - self._start_time
        self._log(
            logging.INFO,
            f"Sandbox ready with {self.num_agents} agents",
            total_duration_ms=(total_time * 1000),
            step_times={k: f"{v*1000:.0f}ms" for k, v in step_times.items()}
        )

        return self.sandbox_id

    except CloudSandboxError:
        # Re-raise our own errors
        raise

    except Exception as e:
        # Wrap unexpected errors
        self._log(
            logging.ERROR,
            f"Unexpected error during sandbox creation: {str(e)}",
            error_type=type(e).__name__
        )
        raise CloudSandboxError(
            message=f"Unexpected error: {str(e)}",
            sandbox_id=self.sandbox_id,
            step="unknown",
            original_error=e
        ) from e

    finally:
        # Always attempt cleanup on failure
        if self.sandbox and not self.sandbox_id:
            self._log(logging.WARNING, "Cleaning up failed sandbox creation")
            try:
                await self.cleanup()
            except Exception as cleanup_error:
                self._log(
                    logging.ERROR,
                    f"Cleanup after failed creation also failed: {cleanup_error}"
                )
```

---

## 13. Final Recommendations

### For Immediate Hackathon Deployment

**DO:**
- Implement all CRITICAL fixes (especially timeouts and cleanup)
- Add basic logging and metrics
- Add health checks
- Test with real E2B sandboxes before hackathon
- Monitor E2B quota usage closely
- Have fallback plan if quota exceeded

**DON'T:**
- Deploy without timeout protection
- Skip error handling improvements
- Ignore rate limiting
- Run without monitoring

### For Long-Term Production

**Invest In:**
- Comprehensive integration testing
- Load testing with multiple concurrent sandboxes
- Security audit of command execution
- Monitoring dashboards for metrics
- Automated alerting on failures
- Documentation for debugging common issues

---

## File Locations Referenced

- **Main File:** `/Users/boris/work/aspire11/claude-swarm/src/claudeswarm/cloud/e2b_launcher.py`
- **Tests:** `/Users/boris/work/aspire11/claude-swarm/tests/test_cloud_e2b_launcher.py`
- **Types:** `/Users/boris/work/aspire11/claude-swarm/src/claudeswarm/cloud/types.py`
- **MCP Bridge:** `/Users/boris/work/aspire11/claude-swarm/src/claudeswarm/cloud/mcp_bridge.py`
- **Config:** `/Users/boris/work/aspire11/claude-swarm/.env.example`

---

**Review Complete:** The code has a solid foundation but requires critical hardening for production use. Focus on the Phase 1 fixes immediately, then tackle Phase 2 during hackathon preparation.
