# Claude Swarm - Quick Start

## How It Works

1. **You** create a tmux session with multiple Claude Code instances
2. All agents work in the **same project directory**
3. Run **one script** to introduce them and enable coordination
4. Agents can now communicate and coordinate file access!

## Steps

### Step 1: Create Your Tmux Session

```bash
# Create tmux session however you like
tmux new -s myproject

# Split into multiple panes (Ctrl+b % or Ctrl+b ")
# Start Claude Code in each pane
# Make sure all are in the SAME project directory!
```

### Step 2: Run Onboarding Script

```bash
./onboard.sh /path/to/your/project
```

For example:
```bash
./onboard.sh ~/work/aspire11/podcasts-chatbot
```

This will:
- ✅ Discover all agents in your project
- ✅ Introduce them to each other
- ✅ Tell them how to coordinate
- ✅ Start the dashboard at http://localhost:8080

### Step 3: Done!

The agents now know:
- How to read messages from other agents
- How to send messages
- How to lock files before editing
- How to unlock files after editing

They will receive instructions in their message log and can start coordinating immediately!

## Agent Commands

Each agent can use these commands (they'll be told this automatically):

```bash
# Read messages
python3 coord.py YOUR_ID read

# Send message
python3 coord.py YOUR_ID send OTHER_ID "message"

# Lock file
python3 coord.py YOUR_ID lock path/to/file "reason"

# Unlock file
python3 coord.py YOUR_ID unlock path/to/file
```

## Monitor

Watch live coordination at: **http://localhost:8080**

## That's It!

The system automatically:
- Works with any project directory
- Discovers agents in tmux
- Handles messaging and file locking
- Provides a web dashboard

Just create your tmux session and run `./onboard.sh /your/project`!
