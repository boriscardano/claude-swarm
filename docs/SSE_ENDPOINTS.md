# Server-Sent Events (SSE) Endpoints Specification

## Overview

This document specifies the enhanced SSE endpoints needed for the Cloud-Native Dashboard (Hours 9-10). These endpoints provide real-time updates for autonomous multi-agent development in E2B sandboxes.

**Implemented by:** agent-5 (specification), ALL (implementation in Hour 9-10)

---

## Current SSE Implementation

### Existing Endpoint: `/api/stream`

**Location:** `src/claudeswarm/web/server.py:392`

**Current Events:**
- `connected`: Initial connection confirmation
- `agents`: Active agents list updates
- `locks`: File locks updates
- `messages`: New message notifications
- `stats`: System statistics
- `heartbeat`: Keep-alive ping
- `error`: Error notifications

**Polling Interval:** 1 second

**Event Format:**
```
event: <event_type>
data: <json_payload>

```

---

## New Cloud-Specific Endpoints

### 1. `/api/cloud/sandbox-status`

**Purpose:** Real-time E2B sandbox metrics and health

**Method:** GET

**Response Type:** Server-Sent Events (SSE)

**Event Types:**

#### Event: `sandbox-info`
```json
{
  "sandbox_id": "e2b-abc123",
  "status": "running",
  "uptime_seconds": 3600,
  "cost_estimate_usd": 0.45,
  "created_at": "2025-11-19T12:00:00Z"
}
```

#### Event: `resources`
```json
{
  "cpu_percent": 23.5,
  "memory_mb": 512,
  "memory_percent": 25.6,
  "disk_mb": 1024,
  "disk_percent": 15.3
}
```

#### Event: `mcp-status`
```json
{
  "mcps": [
    {
      "name": "github",
      "status": "connected",
      "container_id": "abc123",
      "uptime_seconds": 3500,
      "request_count": 45,
      "error_count": 2,
      "last_request_at": "2025-11-19T12:30:00Z"
    },
    {
      "name": "exa",
      "status": "connected",
      "container_id": "def456",
      "uptime_seconds": 3500,
      "request_count": 12,
      "error_count": 0,
      "last_request_at": "2025-11-19T12:29:45Z"
    }
  ]
}
```

**Polling Interval:** 2 seconds

**Implementation:**
```python
@app.get("/api/cloud/sandbox-status")
async def cloud_sandbox_status() -> StreamingResponse:
    """
    Stream real-time E2B sandbox status and metrics.

    Returns:
        StreamingResponse with SSE events for sandbox info, resources, and MCP status
    """

    async def generate_sandbox_events() -> AsyncGenerator[str, None]:
        from claudeswarm.cloud import get_active_sandbox, MCPBridge

        yield f"event: connected\ndata: {json.dumps({'status': 'connected'})}\n\n"

        while True:
            try:
                # Get sandbox instance
                sandbox = get_active_sandbox()
                if not sandbox:
                    yield f"event: error\ndata: {json.dumps({'error': 'No active sandbox'})}\n\n"
                    await asyncio.sleep(2.0)
                    continue

                # Send sandbox info
                sandbox_info = {
                    "sandbox_id": sandbox.sandbox_id,
                    "status": sandbox.status,
                    "uptime_seconds": sandbox.get_uptime(),
                    "cost_estimate_usd": sandbox.estimate_cost(),
                    "created_at": sandbox.created_at
                }
                yield f"event: sandbox-info\ndata: {json.dumps(sandbox_info)}\n\n"

                # Send resource metrics
                resources = await sandbox.get_resources()
                yield f"event: resources\ndata: {json.dumps(resources)}\n\n"

                # Send MCP status
                bridge = sandbox.get_mcp_bridge()
                if bridge:
                    mcp_status = await bridge.get_all_mcp_status()
                    yield f"event: mcp-status\ndata: {json.dumps(mcp_status)}\n\n"

                await asyncio.sleep(2.0)

            except asyncio.CancelledError:
                break
            except Exception as e:
                error_data = {"error": str(e)}
                yield f"event: error\ndata: {json.dumps(error_data)}\n\n"
                await asyncio.sleep(2.0)

    return StreamingResponse(
        generate_sandbox_events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
```

---

### 2. `/api/cloud/agent-conversations`

**Purpose:** Real-time agent message feed with conversation threading

**Method:** GET

**Query Parameters:**
- `thread_id` (optional): Filter by conversation thread
- `agent_id` (optional): Filter by specific agent
- `since` (optional): Only messages after timestamp

**Response Type:** Server-Sent Events (SSE)

**Event Types:**

#### Event: `message`
```json
{
  "id": "msg-123",
  "thread_id": "debate-bcrypt-vs-argon2",
  "timestamp": "2025-11-19T12:30:15Z",
  "sender_id": "agent-3",
  "recipient_id": "agent-1",
  "msg_type": "challenge",
  "content": "Why bcrypt over argon2? Research suggests argon2 is more secure.",
  "metadata": {
    "in_reply_to": "msg-120",
    "evidence_urls": ["https://example.com/argon2-benchmark"]
  }
}
```

#### Event: `thread-created`
```json
{
  "thread_id": "debate-bcrypt-vs-argon2",
  "topic": "Password hashing algorithm selection",
  "participants": ["agent-1", "agent-3"],
  "created_at": "2025-11-19T12:28:00Z",
  "status": "active"
}
```

#### Event: `thread-resolved`
```json
{
  "thread_id": "debate-bcrypt-vs-argon2",
  "resolution": "consensus",
  "outcome": "argon2 selected with 3 votes vs 1",
  "resolved_at": "2025-11-19T12:35:00Z"
}
```

**Polling Interval:** 0.5 seconds (real-time message feed)

**Implementation:**
```python
@app.get("/api/cloud/agent-conversations")
async def cloud_agent_conversations(
    thread_id: Optional[str] = None,
    agent_id: Optional[str] = None,
    since: Optional[str] = None
) -> StreamingResponse:
    """
    Stream real-time agent conversations with threading support.

    Args:
        thread_id: Optional conversation thread to filter
        agent_id: Optional agent to filter messages from
        since: Optional ISO timestamp to get messages after

    Returns:
        StreamingResponse with SSE events for messages, thread events
    """

    async def generate_conversation_events() -> AsyncGenerator[str, None]:
        from claudeswarm.messaging import ConversationThread

        # Track last seen message ID to avoid duplicates
        last_message_id = None
        seen_threads = set()

        yield f"event: connected\ndata: {json.dumps({'status': 'connected'})}\n\n"

        while True:
            try:
                # Get new messages
                messages = get_messages_since(
                    last_message_id=last_message_id,
                    thread_id=thread_id,
                    agent_id=agent_id,
                    since=since
                )

                for msg in messages:
                    # Detect and announce new threads
                    if msg.get('thread_id') and msg['thread_id'] not in seen_threads:
                        thread_info = get_thread_info(msg['thread_id'])
                        yield f"event: thread-created\ndata: {json.dumps(thread_info)}\n\n"
                        seen_threads.add(msg['thread_id'])

                    # Send message
                    yield f"event: message\ndata: {json.dumps(msg)}\n\n"
                    last_message_id = msg['id']

                # Check for resolved threads
                resolved = get_resolved_threads_since(last_check)
                for thread in resolved:
                    yield f"event: thread-resolved\ndata: {json.dumps(thread)}\n\n"

                await asyncio.sleep(0.5)

            except asyncio.CancelledError:
                break
            except Exception as e:
                error_data = {"error": str(e)}
                yield f"event: error\ndata: {json.dumps(error_data)}\n\n"
                await asyncio.sleep(0.5)

    return StreamingResponse(
        generate_conversation_events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
```

---

### 3. `/api/cloud/mcp-calls`

**Purpose:** Real-time log of MCP method calls and responses

**Method:** GET

**Query Parameters:**
- `mcp_name` (optional): Filter by MCP (github, exa, etc.)
- `since` (optional): Only calls after timestamp

**Response Type:** Server-Sent Events (SSE)

**Event Types:**

#### Event: `mcp-call-start`
```json
{
  "call_id": "call-789",
  "mcp_name": "exa",
  "method": "web_search_exa",
  "params": {
    "query": "JWT best practices Python",
    "num_results": 5
  },
  "started_at": "2025-11-19T12:30:00Z",
  "agent_id": "agent-1"
}
```

#### Event: `mcp-call-complete`
```json
{
  "call_id": "call-789",
  "mcp_name": "exa",
  "method": "web_search_exa",
  "success": true,
  "duration_ms": 2340,
  "result_summary": "Found 5 results about JWT best practices",
  "completed_at": "2025-11-19T12:30:02Z"
}
```

#### Event: `mcp-call-error`
```json
{
  "call_id": "call-790",
  "mcp_name": "github",
  "method": "create_pull_request",
  "success": false,
  "error": "Rate limit exceeded",
  "duration_ms": 450,
  "retry_count": 3,
  "failed_at": "2025-11-19T12:31:15Z"
}
```

#### Event: `mcp-stats`
```json
{
  "window_minutes": 5,
  "stats": {
    "github": {
      "total_calls": 12,
      "successful_calls": 10,
      "failed_calls": 2,
      "avg_duration_ms": 850,
      "rate_limit_remaining": 18
    },
    "exa": {
      "total_calls": 8,
      "successful_calls": 8,
      "failed_calls": 0,
      "avg_duration_ms": 2100,
      "rate_limit_remaining": 12
    }
  }
}
```

**Polling Interval:** 1 second

**Implementation:**
```python
@app.get("/api/cloud/mcp-calls")
async def cloud_mcp_calls(
    mcp_name: Optional[str] = None,
    since: Optional[str] = None
) -> StreamingResponse:
    """
    Stream real-time MCP call log with success/failure tracking.

    Args:
        mcp_name: Optional MCP to filter calls for
        since: Optional ISO timestamp to get calls after

    Returns:
        StreamingResponse with SSE events for MCP calls and statistics
    """

    async def generate_mcp_call_events() -> AsyncGenerator[str, None]:
        from claudeswarm.cloud import MCPCallLogger

        last_call_id = None
        stats_interval = 5  # Send stats every 5 iterations

        yield f"event: connected\ndata: {json.dumps({'status': 'connected'})}\n\n"

        iteration = 0
        while True:
            try:
                # Get recent calls
                calls = MCPCallLogger.get_calls_since(
                    last_call_id=last_call_id,
                    mcp_name=mcp_name,
                    since=since
                )

                for call in calls:
                    # Determine event type
                    if call['status'] == 'started':
                        event_type = 'mcp-call-start'
                    elif call['status'] == 'completed' and call['success']:
                        event_type = 'mcp-call-complete'
                    else:
                        event_type = 'mcp-call-error'

                    yield f"event: {event_type}\ndata: {json.dumps(call)}\n\n"
                    last_call_id = call['call_id']

                # Send stats periodically
                iteration += 1
                if iteration % stats_interval == 0:
                    stats = MCPCallLogger.get_stats(window_minutes=5)
                    yield f"event: mcp-stats\ndata: {json.dumps(stats)}\n\n"

                await asyncio.sleep(1.0)

            except asyncio.CancelledError:
                break
            except Exception as e:
                error_data = {"error": str(e)}
                yield f"event: error\ndata: {json.dumps(error_data)}\n\n"
                await asyncio.sleep(1.0)

    return StreamingResponse(
        generate_mcp_call_events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
```

---

## Data Models

### Message Threading

**Location:** `src/claudeswarm/messaging.py` (enhancement needed)

```python
@dataclass
class ConversationThread:
    """Represents a conversation thread between agents."""

    thread_id: str
    topic: str
    participants: list[str]
    created_at: str
    status: str  # "active", "resolved", "abandoned"
    resolution: Optional[str] = None
    outcome: Optional[str] = None

@dataclass
class ThreadedMessage:
    """Message with threading metadata."""

    id: str
    thread_id: Optional[str]
    in_reply_to: Optional[str]
    # ... existing message fields ...
```

### MCP Call Logging

**Location:** `src/claudeswarm/cloud/mcp_logger.py` (new file needed)

```python
class MCPCallLogger:
    """Centralized logging for all MCP calls."""

    _instance = None
    _calls_log: list[dict] = []

    @classmethod
    def log_call_start(cls, mcp_name: str, method: str, params: dict, agent_id: str) -> str:
        """Log the start of an MCP call."""
        call_id = f"call-{uuid.uuid4().hex[:8]}"
        call_record = {
            "call_id": call_id,
            "mcp_name": mcp_name,
            "method": method,
            "params": params,
            "started_at": datetime.utcnow().isoformat(),
            "agent_id": agent_id,
            "status": "started"
        }
        cls._calls_log.append(call_record)
        return call_id

    @classmethod
    def log_call_complete(cls, call_id: str, success: bool, result: Any, duration_ms: float):
        """Log the completion of an MCP call."""
        # Find and update call record
        ...

    @classmethod
    def get_calls_since(cls, last_call_id: Optional[str] = None, **filters) -> list[dict]:
        """Get calls since a specific call ID."""
        ...

    @classmethod
    def get_stats(cls, window_minutes: int = 5) -> dict:
        """Get statistics for recent calls."""
        ...
```

---

## Frontend Integration

### EventSource Setup

```javascript
// Connect to sandbox status stream
const sandboxStream = new EventSource('/api/cloud/sandbox-status');

sandboxStream.addEventListener('sandbox-info', (event) => {
    const data = JSON.parse(event.data);
    updateSandboxInfo(data);
});

sandboxStream.addEventListener('resources', (event) => {
    const data = JSON.parse(event.data);
    updateResourceMetrics(data);
});

sandboxStream.addEventListener('mcp-status', (event) => {
    const data = JSON.parse(event.data);
    updateMCPStatus(data);
});

// Connect to conversations stream
const conversationsStream = new EventSource('/api/cloud/agent-conversations');

conversationsStream.addEventListener('message', (event) => {
    const msg = JSON.parse(event.data);
    appendMessage(msg);
});

conversationsStream.addEventListener('thread-created', (event) => {
    const thread = JSON.parse(event.data);
    createThreadView(thread);
});

conversationsStream.addEventListener('thread-resolved', (event) => {
    const resolution = JSON.parse(event.data);
    markThreadResolved(resolution);
});

// Connect to MCP calls stream
const mcpCallsStream = new EventSource('/api/cloud/mcp-calls');

mcpCallsStream.addEventListener('mcp-call-start', (event) => {
    const call = JSON.parse(event.data);
    showCallInProgress(call);
});

mcpCallsStream.addEventListener('mcp-call-complete', (event) => {
    const call = JSON.parse(event.data);
    showCallSuccess(call);
});

mcpCallsStream.addEventListener('mcp-call-error', (event) => {
    const call = JSON.parse(event.data);
    showCallError(call);
});
```

---

## Dashboard UI Components

### 1. Cloud Sandbox Panel
```
┌─────────────────────────────────────────┐
│ E2B Sandbox: e2b-abc123         [●]     │
│ ───────────────────────────────────────  │
│ Status: Running                          │
│ Uptime: 1h 15m                          │
│ Cost: $0.45                             │
│                                         │
│ Resources:                               │
│ CPU:    23.5% [████████░░░░░░]          │
│ Memory: 512MB (25.6%) [█████░░░░░]      │
│ Disk:   1GB (15.3%) [███░░░░░░░░]       │
└─────────────────────────────────────────┘
```

### 2. MCP Status Panel
```
┌─────────────────────────────────────────┐
│ MCP Servers                             │
│ ───────────────────────────────────────  │
│ ✓ GitHub       45 calls  2 errors       │
│ ✓ Exa          12 calls  0 errors       │
│ ✓ Filesystem   89 calls  0 errors       │
│ ✓ Perplexity    5 calls  0 errors       │
└─────────────────────────────────────────┘
```

### 3. Agent Conversations View
```
┌─────────────────────────────────────────┐
│ Conversations                           │
│ ───────────────────────────────────────  │
│ 🔥 Debate: bcrypt vs argon2 [ACTIVE]    │
│    agent-3 → agent-1                    │
│    "Why bcrypt over argon2? Research..." │
│    3 messages, 2 participants           │
│                                         │
│ ✅ Review: JWT implementation [RESOLVED] │
│    Outcome: Approved with suggestions   │
│    5 messages, 3 participants           │
└─────────────────────────────────────────┘
```

### 4. MCP Call Log
```
┌─────────────────────────────────────────┐
│ Recent MCP Calls                        │
│ ───────────────────────────────────────  │
│ ⏳ exa.web_search_exa                    │
│    Query: "JWT best practices..."       │
│    Started 2s ago by agent-1            │
│                                         │
│ ✓ github.commit_files (850ms)           │
│    5 files committed by agent-2         │
│                                         │
│ ✗ github.create_pr (450ms)              │
│    Rate limit exceeded (retry 3/3)      │
└─────────────────────────────────────────┘
```

---

## Testing

### Manual Testing
```bash
# Test sandbox status endpoint
curl -N http://localhost:8000/api/cloud/sandbox-status

# Test conversations endpoint
curl -N http://localhost:8000/api/cloud/agent-conversations

# Test MCP calls endpoint
curl -N http://localhost:8000/api/cloud/mcp-calls?mcp_name=github
```

### Load Testing
```python
import asyncio
from httpx import AsyncClient

async def test_sse_load():
    async with AsyncClient() as client:
        tasks = [
            client.stream("GET", "http://localhost:8000/api/cloud/sandbox-status")
            for _ in range(100)  # 100 concurrent connections
        ]
        await asyncio.gather(*tasks)
```

---

## Implementation Checklist (Hour 9-10)

### Backend (server.py)
- [ ] Add `/api/cloud/sandbox-status` endpoint
- [ ] Add `/api/cloud/agent-conversations` endpoint
- [ ] Add `/api/cloud/mcp-calls` endpoint
- [ ] Implement `MCPCallLogger` class
- [ ] Add conversation threading to messaging system
- [ ] Test all endpoints with curl

### Frontend (static/index.html or new file)
- [ ] Create Cloud Sandbox Panel component
- [ ] Create MCP Status Panel component
- [ ] Create Agent Conversations View component
- [ ] Create MCP Call Log component
- [ ] Implement EventSource connections
- [ ] Add real-time updates to UI
- [ ] Test with live data

### Integration
- [ ] Connect `MCPBridge` to `MCPCallLogger`
- [ ] Update `CloudSandbox` to expose metrics
- [ ] Test end-to-end with running sandbox
- [ ] Verify performance with 4 agents + 4 MCPs

---

## Performance Considerations

### Connection Limits
- Maximum 100 concurrent SSE connections per endpoint
- Implement connection pooling for high traffic
- Use nginx buffering disabled (`X-Accel-Buffering: no`)

### Data Volume
- Limit message history to last 1000 messages
- Compress large payloads (gzip)
- Implement client-side caching

### Scalability
- Use Redis for cross-instance SSE (if needed)
- Implement backpressure handling
- Monitor memory usage for long-running connections

---

**Last Updated:** 2025-11-19 by agent-5
**Status:** Specification Complete - Ready for Implementation
**Implementation Window:** Hackathon Day 2, Hours 9-10
