# E2B Transparent Shell - Vision & Goals

## User Experience Goal

The ideal user workflow should be:

```bash
# 1. User opens terminal and deploys
$ claudeswarm cloud deploy

🚀 Creating E2B sandbox...
✓ Sandbox created: ij6u7c62v31z3b99kwji9
📦 Installing dependencies...
✓ All set up!

🔌 Connecting to sandbox...

# 2. User is now automatically in the E2B sandbox
ij6u7c62:~$ pwd
/home/user

# 3. User clones their repo
ij6u7c62:~$ git clone https://github.com/myuser/myrepo
Cloning into 'myrepo'...

# 4. User creates tmux panes naturally
ij6u7c62:~$ cd myrepo
ij6u7c62:~/myrepo$ tmux new-session -s work
# Creates panes with Ctrl+B %

# 5. User runs Claude Code agents in different panes
# Pane 1
ij6u7c62:~/myrepo$ claudeswarm onboard --role backend

# Pane 2
ij6u7c62:~/myrepo$ claudeswarm onboard --role frontend

# 6. Agents coordinate and work together
# Everything runs in the E2B sandbox but feels completely local!
```

## Key Requirements

1. **Automatic Connection**: After `deploy`, user is automatically dropped into sandbox shell
2. **Transparent Experience**: User doesn't think about E2B - it feels like local terminal
3. **Persistent State**: cd, environment variables, etc. persist across commands
4. **Full tmux Support**: User can create/manage tmux sessions inside the sandbox
5. **Multi-Pane Workflow**: Multiple local panes can connect to same sandbox
6. **Agent Coordination**: Claude Code agents run inside sandbox and coordinate
7. **Easy Disconnect**: User can exit shell but sandbox keeps running
8. **Easy Reconnect**: User can reconnect to running sandbox anytime

## Implementation Status

### ✅ Completed
- [x] E2B sandbox creation and setup
- [x] uv-based fast dependency installation
- [x] Tmux setup with multiple panes inside sandbox
- [x] Agent discovery system
- [x] Basic shell command (`claudeswarm cloud shell`)
- [x] Transparent shell wrapper script (`e2b_tmux_shell.py`)

### 🚧 In Progress
- [ ] Auto-connect after deploy
- [ ] Directory persistence (cd tracking)
- [ ] Better prompt customization

### 📋 Todo
- [ ] Multi-pane reconnect support
- [ ] Shell history persistence
- [ ] Environment variable persistence
- [ ] File upload/download helpers
- [ ] Port forwarding for web apps
- [ ] Integration with Claude Code Claude agent SDK

## Architecture

```
┌─────────────────────────────────────────────────────┐
│           User's Local Machine                       │
│                                                      │
│  Terminal 1           Terminal 2           Terminal 3│
│  ┌──────────┐        ┌──────────┐        ┌────────┐│
│  │ Shell    │        │ Shell    │        │ Shell  ││
│  │ Wrapper  │        │ Wrapper  │        │ Wrapper││
│  └────┬─────┘        └────┬─────┘        └────┬───┘│
│       │                   │                    │    │
│       └───────────────────┼────────────────────┘    │
│                           │                         │
│                    ┌──────▼─────┐                   │
│                    │  E2B API   │                   │
│                    └──────┬─────┘                   │
└────────────────────────────┼─────────────────────────┘
                             │
                ┌────────────▼────────────┐
                │   E2B Sandbox (Cloud)   │
                │                         │
                │  /home/user             │
                │    ├── myrepo/          │
                │    ├── claudeswarm/     │
                │    └── .tmux/           │
                │                         │
                │  tmux sessions:         │
                │    └── work             │
                │         ├── Pane 0 →Agent│
                │         ├── Pane 1 →Agent│
                │         └── Pane 2 →Agent│
                └─────────────────────────┘
```

## Benefits

1. **Zero Local Setup**: No need to install dependencies locally
2. **Consistent Environment**: Same environment for all developers
3. **Cloud Resources**: Use powerful cloud machines for development
4. **Team Collaboration**: Multiple developers can connect to same sandbox
5. **Persistent Workspace**: Sandbox keeps running even if you disconnect
6. **Agent Coordination**: Perfect for multi-agent AI development workflows

## Future Enhancements

- VS Code remote integration
- Jupyter notebook support
- GPU acceleration for AI workloads
- Sandbox templates for different tech stacks
- Team sandbox sharing
- Cost tracking and optimization
