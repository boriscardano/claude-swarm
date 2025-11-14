# Quick Setup Guide - Claude Swarm

## Prerequisites
- Create your own tmux session with 2+ panes
- Start Claude Code in each pane, all in the same project directory

## Step 1: Discover Agents

From anywhere, run:

```bash
source .venv/bin/activate
claudeswarm --project-root /path/to/your/project discover-agents
```

Or set environment variable once:

```bash
export CLAUDESWARM_ROOT=/path/to/your/project
claudeswarm discover-agents
```

## Step 2: Start Dashboard

```bash
claudeswarm --project-root /path/to/your/project start-dashboard
```

## Step 3: Tell Each Agent How to Coordinate

Copy this to each agent in their tmux pane:

```
You are in a multi-agent coordination system.

Your coordination commands (replace YOUR_ID and OTHER_ID):

READ MESSAGES:
python3 coord.py YOUR_ID read

SEND MESSAGE:
python3 coord.py YOUR_ID send OTHER_ID "message"

LOCK FILE:
python3 coord.py YOUR_ID lock path/to/file "reason"

UNLOCK FILE:
python3 coord.py YOUR_ID unlock path/to/file

Dashboard: http://localhost:8080
```

That's it!
