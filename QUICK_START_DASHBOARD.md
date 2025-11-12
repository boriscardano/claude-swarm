# Quick Start: Claude Swarm Dashboard

## 1. Test the UI (No Backend Required)

```bash
# Open the test page with mock data
open /Users/boris/work/aspire11/claude-swarm/src/claudeswarm/web/static/test.html
```

This shows the complete UI with sample data.

## 2. Run Live Dashboard

```bash
# Start the backend server
cd /Users/boris/work/aspire11/claude-swarm
python -m claudeswarm.web.server

# Open browser to:
# http://localhost:8000
```

The dashboard will automatically:
- Load initial data from API
- Connect via Server-Sent Events (SSE)
- Display real-time updates
- Auto-reconnect if connection drops

## Files Overview

```
src/claudeswarm/web/static/
├── index.html      (96 lines)   - Main dashboard page
├── style.css       (697 lines)  - Dark theme styling
├── dashboard.js    (624 lines)  - SSE integration & logic
├── test.html       - Test page with mock data
└── README.md       - Full documentation
```

## What You'll See

**4 Panels:**
1. **Active Agents** - Shows all running agents with status (green/orange/red)
2. **Recent Messages** - Live message feed with color-coded types
3. **Active Locks** - Current file locks held by agents
4. **Statistics** - Key metrics (agents, messages, locks, uptime)

**Features:**
- Real-time updates (no refresh needed)
- Auto-scrolling message feed
- Connection status indicator
- Error recovery with auto-reconnect
- Responsive design (works on mobile)

## Troubleshooting

**Dashboard shows "Connecting...":**
- Backend is not running
- Start with: `python -m claudeswarm.web.server`

**No data showing:**
- No agents are active
- Start some agents with Claude Swarm

**Connection keeps dropping:**
- Check network connectivity
- Dashboard will auto-reconnect up to 5 times

## Next Steps

1. ✅ Test UI with `test.html`
2. ✅ Start backend server
3. ✅ Open live dashboard
4. ✅ Start some Claude Swarm agents
5. ✅ Watch real-time updates!

For full documentation, see `README.md` in the static directory.
