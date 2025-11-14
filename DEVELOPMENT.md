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
