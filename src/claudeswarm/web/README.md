# Claude Swarm Web Dashboard

Real-time monitoring dashboard for Claude Swarm multi-agent coordination system.

## Features

- **Live Agent Monitoring**: View active agents, their status, and session information
- **Lock Management**: Monitor file locks in real-time
- **Message Stream**: View recent inter-agent messages with filtering
- **Real-time Updates**: Server-Sent Events (SSE) for live dashboard updates
- **System Statistics**: Aggregated metrics and agent activity
- **REST API**: Full JSON API for external integrations

## Installation

Install the optional web dependencies:

```bash
pip install -e ".[web]"
# or with uv:
uv pip install -e ".[web]"
```

## Quick Start

### Basic Usage

Start the server from the project root:

```bash
# Set the project root (if not in project directory)
export CLAUDESWARM_ROOT=/path/to/claude-swarm

# Start the server
uvicorn claudeswarm.web.server:app --reload
```

The dashboard will be available at `http://localhost:8000`

### Production Deployment

For production, use multiple workers and proper configuration:

```bash
uvicorn claudeswarm.web.server:app \
  --host 0.0.0.0 \
  --port 8000 \
  --workers 4 \
  --log-level info
```

Or use Gunicorn with uvicorn workers:

```bash
gunicorn claudeswarm.web.server:app \
  --workers 4 \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000 \
  --access-logfile -
```

## API Endpoints

### Dashboard & Static Files

- `GET /` - Main dashboard interface (HTML)
- `GET /static/{path}` - Static assets (CSS, JS)

### REST API (v1)

- `GET /api/v1/agents` - List all active agents
- `GET /api/v1/locks` - List all active file locks
- `GET /api/v1/messages?limit=50` - Get recent messages (default: 50)
- `GET /api/v1/stats` - Get system statistics
- `GET /health` - Health check endpoint

### Legacy API (Redirects)

For backwards compatibility, the following legacy endpoints redirect to v1:

- `GET /api/agents` → `/api/v1/agents` (307 redirect)
- `GET /api/locks` → `/api/v1/locks` (307 redirect)
- `GET /api/messages` → `/api/v1/messages` (307 redirect)
- `GET /api/stats` → `/api/v1/stats` (307 redirect)
- `GET /api/stream` → `/api/v1/stream` (307 redirect)

### Real-time Streaming

- `GET /api/v1/stream` - Server-Sent Events stream for live updates

### API Documentation

- `GET /docs` - Interactive Swagger UI documentation
- `GET /redoc` - Alternative ReDoc documentation

## Configuration

### Environment Variables

- `CLAUDESWARM_ROOT` - Project root directory (default: auto-detected from package location)
- `UVICORN_HOST` - Server host (default: 0.0.0.0)
- `UVICORN_PORT` - Server port (default: 8000)

### Data Sources

The server monitors these files in the project root:

- `ACTIVE_AGENTS.json` - Active agent registry
- `agent_messages.log` - Inter-agent message log
- `.agent_locks/` - Directory containing lock files

## API Examples

### Get Active Agents

```bash
curl http://localhost:8000/api/v1/agents
```

Response:
```json
{
  "session_name": "0",
  "updated_at": "2025-11-07T15:35:45.420255+00:00",
  "agents": [
    {
      "id": "agent-0",
      "pane_index": "0:1.1",
      "pid": 2256,
      "status": "active",
      "last_seen": "2025-11-07T15:35:45.420255+00:00"
    }
  ]
}
```

### Get System Statistics

```bash
curl http://localhost:8000/api/v1/stats
```

Response:
```json
{
  "agent_count": 3,
  "lock_count": 0,
  "message_count": 10,
  "message_types": {"INFO": 10},
  "latest_activity": "2025-11-07T16:35:45.973823",
  "session_name": "0"
}
```

### Stream Live Updates

```bash
curl -N http://localhost:8000/api/v1/stream
```

Response (SSE format):
```
event: connected
data: {"status": "connected", "timestamp": "2025-11-10T14:26:55.516909"}

event: agents
data: {"session_name": "0", "agents": [...]}

event: stats
data: {"agent_count": 3, "lock_count": 0, ...}

event: heartbeat
data: {"timestamp": "2025-11-10T14:26:56.520257"}
```

## Development

### Running in Development Mode

```bash
# With auto-reload
uvicorn claudeswarm.web.server:app --reload --log-level debug

# Or use the direct Python entry point
python -m claudeswarm.web.server
```

### Testing the API

A test script is provided in the project root:

```bash
# Start the server first
uvicorn claudeswarm.web.server:app &

# Run the test script
python test_api_server.py
```

### CORS Configuration

By default, CORS is enabled for all origins in development. For production, update the `CORSMiddleware` configuration in `server.py`:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://yourdomain.com"],  # Specify exact origins
    allow_credentials=True,
    allow_methods=["GET"],
    allow_headers=["*"],
)
```

## Architecture

### Async-First Design

The server uses FastAPI's async capabilities for optimal performance:

- Async file I/O for log tailing and JSON parsing
- Non-blocking SSE streams for real-time updates
- Efficient connection pooling

### Error Handling

The server gracefully handles:

- Missing or corrupt data files (returns empty results)
- Client disconnections in SSE streams
- File permission errors
- JSON parsing failures

### Performance

- File change detection using mtime tracking (no polling)
- Efficient log tailing (reads last N lines only)
- Response caching opportunities for read-heavy workloads
- Low memory footprint (~50MB baseline)

## Monitoring

### Health Checks

The `/health` endpoint provides service health status:

```bash
curl http://localhost:8000/health
```

Use this endpoint for:
- Load balancer health checks
- Kubernetes liveness/readiness probes
- Monitoring system integration

### Metrics

For production monitoring, integrate with:
- Prometheus (use `prometheus-fastapi-instrumentator`)
- DataDog APM
- New Relic
- Sentry for error tracking

## Security Considerations

### Production Checklist

- [ ] Update CORS origins to specific domains
- [ ] Use HTTPS with proper TLS certificates
- [ ] Enable rate limiting (e.g., using `slowapi`)
- [ ] Add authentication middleware if needed
- [ ] Configure security headers
- [ ] Run behind a reverse proxy (nginx, Caddy)
- [ ] Enable access logging
- [ ] Set up monitoring and alerting

### Authentication

To add authentication, use FastAPI dependencies:

```python
from fastapi import Depends, HTTPException, Security
from fastapi.security import HTTPBearer

security = HTTPBearer()

async def verify_token(credentials = Security(security)):
    # Implement token verification
    pass

@api_v1.get("/agents", dependencies=[Depends(verify_token)])
async def get_agents():
    ...
```

## Troubleshooting

### Server won't start

1. Check if port 8000 is available:
   ```bash
   lsof -i :8000
   ```

2. Verify Python and dependencies:
   ```bash
   python --version  # Should be 3.12+
   pip list | grep fastapi
   ```

3. Check PYTHONPATH and CLAUDESWARM_ROOT:
   ```bash
   echo $PYTHONPATH
   echo $CLAUDESWARM_ROOT
   ```

### Data not showing

1. Verify file locations:
   ```bash
   ls -la ACTIVE_AGENTS.json
   ls -la agent_messages.log
   ls -la .agent_locks/
   ```

2. Check file permissions:
   ```bash
   stat ACTIVE_AGENTS.json
   ```

3. Test health endpoint:
   ```bash
   curl http://localhost:8000/health
   ```

### SSE stream disconnecting

- Check for reverse proxy buffering (disable with `X-Accel-Buffering: no`)
- Verify firewall/load balancer timeout settings
- Use keep-alive connections

## License

MIT License - see LICENSE file for details
