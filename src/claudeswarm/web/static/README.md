# Claude Swarm Dashboard - Frontend

Modern, real-time monitoring dashboard for Claude Swarm multi-agent system.

## Files

- **index.html** (96 lines) - Main dashboard HTML structure
- **style.css** (697 lines) - Professional dark-theme styling
- **dashboard.js** (550 lines) - JavaScript with SSE and API integration
- **test.html** - Standalone test page with mock data

## Features

### 4-Panel Layout
1. **Active Agents** - Shows all agents with status indicators (active/stale/dead)
2. **Recent Messages** - Real-time message feed with color-coded message types
3. **Active Locks** - Displays current file locks and holders
4. **Statistics** - Key metrics (agents, messages, locks, uptime)

### Real-time Updates
- Server-Sent Events (SSE) for live updates
- Auto-reconnection with exponential backoff
- Connection status indicator
- Automatic timestamp updates

### Message Types
- **QUESTION** - Blue - Agent asking for help
- **BLOCKED** - Red - Agent blocked on a task
- **COMPLETED** - Green - Task completed
- **INFO** - Gray - Informational messages
- **ACK** - Yellow/Orange - Acknowledgment
- **REVIEW_REQUEST** - Purple - Code review requests

### Agent Status
- **Active** - Green dot - Heartbeat < 30s ago
- **Stale** - Orange dot - Heartbeat 30s-2m ago
- **Dead** - Red dot - Heartbeat > 2m ago

## API Endpoints

The dashboard expects these endpoints:

```
GET  /api/agents    - List of active agents
GET  /api/messages  - Recent messages
GET  /api/locks     - Active locks
GET  /api/stats     - System statistics
GET  /api/stream    - SSE stream for real-time updates
```

### Response Formats

**Agents:**
```json
{
  "agents": [
    {
      "agent_id": "agent-0",
      "pid": 12345,
      "last_heartbeat": "2025-11-10T15:24:30Z"
    }
  ]
}
```

**Messages:**
```json
{
  "messages": [
    {
      "sender": "agent-0",
      "msg_type": "QUESTION",
      "content": "Message text",
      "timestamp": "2025-11-10T15:24:30Z"
    }
  ]
}
```

**Locks:**
```json
{
  "locks": [
    {
      "resource": "src/auth.py",
      "holder": "agent-1",
      "acquired_at": "2025-11-10T15:24:30Z"
    }
  ]
}
```

**Stats:**
```json
{
  "active_agents": 3,
  "total_messages": 45,
  "active_locks": 2,
  "uptime": 4980
}
```

**SSE Events:**
```json
{
  "type": "message",
  "message": { /* message object */ }
}

{
  "type": "agents",
  "agents": [ /* agent list */ ]
}
```

## Testing

### Local Testing (Mock Data)
Open `test.html` in a browser to see the dashboard with mock data:
```bash
open test.html
```

### Testing with Backend
1. Start the backend server (Agent 1's work)
2. Open `index.html` via the server's static file endpoint
3. Dashboard will connect via SSE and display real data

## Design Principles

- **Clean & Minimal** - Focus on data, not decoration
- **Dark Theme** - Easy on the eyes for long monitoring sessions
- **Responsive** - Works on desktop, tablet, and mobile
- **Auto-refresh** - No manual refresh needed
- **Error Handling** - Graceful degradation and reconnection

## Browser Compatibility

Tested in:
- Chrome 120+
- Firefox 120+
- Safari 17+

Requires:
- CSS Grid support
- EventSource API (SSE)
- ES6+ JavaScript

## Customization

### Colors
Edit CSS variables in `style.css`:
```css
:root {
  --msg-question: #4a9eff;
  --msg-blocked: #ff4757;
  /* ... etc ... */
}
```

### Update Frequency
Edit `dashboard.js`:
```javascript
// Timestamp updates (default: 10s)
setInterval(() => {
  this.updateTimestampsInDOM();
}, 10000);

// Reconnection delay (default: 2s)
this.reconnectDelay = 2000;
```

## Integration Notes

The frontend is designed to work with the Flask backend from Agent 1. Make sure:
1. Backend serves static files from this directory
2. API endpoints match the expected format
3. SSE stream sends proper event structure
4. CORS is configured if frontend/backend on different ports

## Performance

- Message cache limited to 100 items
- Auto-scroll only when user is at bottom
- Efficient DOM updates (incremental, not full re-render)
- Timestamp updates use cached data
- EventSource auto-reconnects with backoff

## Security Notes

- All user content is HTML-escaped to prevent XSS
- No inline JavaScript in HTML
- Uses Content Security Policy compatible code
- No eval() or Function() constructors
