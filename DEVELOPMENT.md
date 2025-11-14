# Development Guide

## Quick Reload After Code Changes

After making changes to the claudeswarm code, you need to reload the CLI to apply them across all tmux panes.

### Using the Reload Script

**Reload from local changes (recommended for development):**
```bash
./reload.sh
# or
./reload.sh local
# or
make reload
```

**Reload from GitHub (to get the published version):**
```bash
./reload.sh github
# or
make reload-github
```

### What the reload script does:

1. Clears all Python bytecode caches (`__pycache__`, `.pyc` files)
2. Uninstalls the current claudeswarm package
3. Reinstalls from your chosen source:
   - **local**: Editable install from your working directory (changes take effect immediately)
   - **github**: Fresh install from the GitHub repository
4. Verifies the installation

### Available Make Commands

```bash
make help           # Show all available commands
make install        # Initial installation in editable mode
make reload         # Reload with local changes (default)
make reload-local   # Reload with local changes
make reload-github  # Reload from GitHub
make clean          # Clean Python caches and build artifacts
make discover       # Discover active agents
make onboard        # Onboard all agents
make dashboard      # Start web dashboard
```

## Development Workflow

1. **Initial setup:**
   ```bash
   make install
   ```

2. **Make code changes**
   Edit any files in `src/claudeswarm/`

3. **Reload in any tmux pane:**
   ```bash
   make reload
   ```

4. **Test your changes:**
   ```bash
   claudeswarm discover-agents
   claudeswarm onboard
   ```

## Why Reload is Needed

Python caches compiled bytecode (`.pyc` files) for performance. Even with editable installs (`pip install -e .`), different Python processes in different tmux panes may use stale cached bytecode. The reload script ensures:

- All caches are cleared globally
- Fresh Python processes pick up your latest code
- Changes work consistently across all tmux panes

## Troubleshooting

**Changes still not showing up?**
```bash
make clean
make reload
```

**Want to verify which version is installed?**
```bash
pip3 show claude-swarm
```

Look for "Editable project location" to confirm it's using your local code.

## Agent Discovery and Project Filtering

### Overview

Claude Swarm automatically discovers active Claude Code agents running in tmux panes and filters them by project directory. This ensures that only agents working on the current project are coordinated together.

### How Project Filtering Works

1. **Agent Detection**: Scans all tmux panes for Claude Code processes
2. **Process Analysis**: Uses child process scanning to find actual Claude Code binaries
3. **Directory Check**: Determines each agent's current working directory (CWD)
4. **Project Filter**: Only includes agents whose CWD is within the project root

This filtering prevents agents from different projects from interfering with each other, even when running in the same tmux session.

### Platform Support

#### macOS (Full Support)
- Uses `lsof` to determine process CWD
- Requires `lsof` to be installed (comes with macOS by default)
- Full project filtering functionality

#### Linux (Partial Support)
- Process CWD detection not yet implemented
- All discovered agents are included (no directory filtering)
- Future versions will add `/proc/[pid]/cwd` support

#### Windows (Not Supported)
- Requires tmux, which is not available on Windows
- Consider using WSL2 for Windows environments

### How It Works Internally

```python
# 1. Discover all tmux panes
panes = tmux.list_panes()

# 2. Find Claude Code processes
for pane in panes:
    if is_claude_code_process(pane):
        # 3. Get process CWD using lsof (macOS)
        cwd = lsof.get_cwd(pane.pid)

        # 4. Check if CWD is in project
        if is_subdirectory(cwd, project_root):
            # Include this agent
            agents.append(pane)
```

### Logging and Debugging

Enable debug logging to see detailed filtering information:

```bash
export PYTHONPATH=/path/to/claude-swarm/src
python3 -c "
import logging
logging.basicConfig(level=logging.DEBUG)
from claudeswarm.discovery import discover_agents
registry = discover_agents()
print(f'Found {len(registry.agents)} agents')
"
```

Debug logs include:
- Total tmux panes found
- Claude Code processes detected
- Process CWDs and project paths
- Filtering decisions for each agent
- Summary statistics

Example debug output:
```
DEBUG:claudeswarm.discovery:Starting agent discovery (session_name=None, stale_threshold=300s)
DEBUG:claudeswarm.discovery:Found 8 total tmux panes
DEBUG:claudeswarm.discovery:Project root: /Users/user/project
DEBUG:claudeswarm.discovery:Found Claude Code process in pane main:0.1 (PID: 12345)
DEBUG:claudeswarm.discovery:Process 12345 CWD: /Users/user/project/src
DEBUG:claudeswarm.discovery:Process 12345: Working in project (CWD: /Users/user/project/src)
DEBUG:claudeswarm.discovery:Added agent agent-0 for pane main:0.1 (PID: 12345)
DEBUG:claudeswarm.discovery:Agent in pane main:0.2 excluded: working outside project (CWD: /Users/user/other-project)
DEBUG:claudeswarm.discovery:Project filtering summary: 2 Claude processes found, 1 in project, 1 outside project, 0 with unknown CWD
INFO:claudeswarm.discovery:Agent discovery complete: 1 active, 0 stale, 0 removed
```

### Troubleshooting Discovery Issues

#### No agents discovered

**Symptom**: `claudeswarm discover-agents` finds 0 agents

**Possible causes**:
1. **No Claude Code agents running in tmux**
   - Solution: Start Claude Code in a tmux pane
   - Verify: Run `tmux list-panes -a` to see all panes

2. **Agents working in different projects**
   - Solution: Ensure your Claude Code agents are running in the current project directory
   - Check: Agent CWDs must be within the project root
   - Debug: Enable logging to see which agents were filtered out

3. **tmux not running**
   - Solution: Start tmux with `tmux new-session`
   - Verify: Run `tmux list-sessions`

4. **lsof not available (macOS)**
   - Solution: Install lsof (usually comes with macOS)
   - Verify: Run `which lsof`

#### Agents from wrong project included

**Symptom**: Agents working on different projects are being coordinated

**Diagnosis**:
1. Check if filtering is working:
   ```bash
   claudeswarm discover-agents
   cat .claudeswarm/ACTIVE_AGENTS.json
   ```

2. Enable debug logging to see filtering decisions

3. Verify project root detection:
   ```python
   from claudeswarm.project import get_project_root
   print(get_project_root())
   ```

**Possible causes**:
1. **Platform doesn't support CWD detection** (Linux)
   - All agents are included regardless of directory
   - Workaround: Use different tmux sessions per project

2. **Agents share parent directory**
   - If agents are in subdirectories of the same project, they'll all be included
   - This is expected behavior

#### Process CWD cannot be determined

**Symptom**: Debug logs show "Could not determine CWD"

**Possible causes**:
1. **lsof permission issues**
   - Solution: Ensure user has permissions to query process info
   - Test: Run `lsof -a -p $$ -d cwd -Fn`

2. **Process has no CWD**
   - Some processes may not have a working directory
   - These agents will be excluded from discovery

3. **lsof timeout**
   - Slow systems may timeout before lsof completes
   - Check logs for timeout warnings

### Configuration

Agent discovery behavior can be configured in `.claudeswarm/config.toml`:

```toml
[discovery]
# How often to refresh agent registry (seconds)
refresh_interval = 30

# How long before inactive agents are considered stale (seconds)
stale_threshold = 300

# Maximum time to wait for discovery operations (seconds)
timeout = 10
```

### Security Considerations

- Process scanning uses subprocess calls to `ps` and `lsof` with controlled arguments
- Only processes within the project directory are included in the registry
- The claudeswarm process itself is excluded from agent detection
- Registry files are stored in `.claudeswarm/` (add to `.gitignore`)

### Limitations

1. **Platform-dependent CWD detection**
   - macOS: Full support via lsof
   - Linux: Coming soon (will use /proc/[pid]/cwd)
   - Windows: Not supported (no tmux)

2. **Requires tmux**
   - Agents must be running in tmux panes
   - Non-tmux Claude Code instances won't be discovered

3. **CWD-based filtering only**
   - Filtering is based on process working directory
   - Doesn't track which files agents are actually editing
   - If an agent changes directories, it may be filtered differently on next discovery

4. **Process query overhead**
   - Each discovery scans all tmux panes and queries process information
   - May be slow on systems with many panes or slow lsof performance
   - Default refresh interval is 30s to balance freshness and overhead

### Best Practices

1. **Run agents in project root or subdirectories**
   ```bash
   cd /path/to/project
   tmux new-window -c "$(pwd)" claude
   ```

2. **Use separate tmux sessions for different projects**
   ```bash
   tmux new-session -s project1 -c /path/to/project1
   tmux new-session -s project2 -c /path/to/project2
   ```

3. **Monitor the registry file**
   ```bash
   watch -n 5 cat .claudeswarm/ACTIVE_AGENTS.json
   ```

4. **Enable debug logging during development**
   - Helps understand why agents are or aren't being discovered
   - Shows detailed filtering decisions
