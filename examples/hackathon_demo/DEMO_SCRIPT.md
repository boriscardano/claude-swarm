# 2-Minute Demo Script for E2B Hackathon

**Project**: Claude Swarm - Multi-Agent Collaborative Development Platform

**Tagline**: "Finally, AI agents that actually work together"

---

## Pre-Recording Checklist

- [ ] Terminal configured (font size 16+, dark theme)
- [ ] Test repository prepared and accessible
- [ ] E2B API key set in environment
- [ ] Recording software ready (OBS, QuickTime, asciinema)
- [ ] Practice run completed
- [ ] Backup recordings made

---

## Timeline (2:00 total)

### Scene 1: The Hook (0:00 - 0:15)
**Duration**: 15 seconds
**Visual**: Title slide or terminal with intro text

**Script**:
> "Building AI agents is hard. Coordinating multiple agents to work together? Even harder. Most frameworks run locally, can't scale, and struggle with real-world tools. We built Claude Swarm to solve this."

**Technical Notes**:
- Keep it punchy
- Show the problem visually if possible
- Could overlay text on screen

---

### Scene 2: The Setup (0:15 - 0:30)
**Duration**: 15 seconds
**Visual**: Terminal showing deployment

**Command to show**:
```bash
claudeswarm cloud deploy --agents 4 --mcps github,filesystem
```

**Script** (while deployment runs):
> "With one command, we deploy four Claude agents to E2B cloud. Each agent gets access to real tools through the Docker MCP Hub - GitHub for version control, filesystem for code editing."

**Technical Notes**:
- Speed this up in editing (2x speed) if deployment takes too long
- Show key output lines:
  - ✓ Sandbox created
  - ✓ Dependencies installed
  - ✓ Tmux session created with 4 panes
  - ✓ MCPs attached

---

### Scene 3: The Connection (0:30 - 0:40)
**Duration**: 10 seconds
**Visual**: Connecting to sandbox

**Command to show**:
```bash
claudeswarm cloud shell
# Or: e2b sandbox connect <sandbox-id>
```

**Script**:
> "In seconds, we're connected. Let's watch four agents collaborate on a real GitHub repository."

**Technical Notes**:
- Show tmux session with 4 panes
- Quick pan across panes to show they're ready
- Could overlay labels: PM, Backend, Frontend, QA

---

### Scene 4: The Magic (0:40 - 1:30)
**Duration**: 50 seconds (CORE DEMO)
**Visual**: Split screen showing 4 tmux panes + close-ups

**Command to show**:
```bash
# Run in each pane (or use start_demo.sh):
./examples/hackathon_demo/start_demo.sh \
  https://github.com/demo/app \
  "Add dark mode support"
```

**Script** (narrate as agents work):
> "Here's what's happening:
>
> [Point to Pane 0] The Project Manager clones the repository, analyzes the codebase structure, and creates a task breakdown.
>
> [Point to Pane 1] The Backend Developer receives their tasks and starts implementing the dark mode API endpoints.
>
> [Point to Pane 2] Simultaneously, the Frontend Developer creates the theme toggle UI.
>
> [Point to Pane 3] Meanwhile, the QA Engineer waits for their work to finish, then writes tests, validates everything, and pushes the changes to GitHub.
>
> This is true parallel execution. The agents communicate through our messaging system, synchronize their work, and complete the feature as a team."

**Technical Notes**:
- **CRITICAL**: This needs to show actual progress
- Consider showing:
  - Code files being created/modified
  - Git commits
  - Message passing between agents
- Use zoom/close-ups on interesting moments
- Speed up boring parts (but keep narration normal speed)
- Show status updates from each agent

**What viewers should see**:
```
Pane 0 (PM):
  📋 [PM] Starting project management tasks...
  📦 [PM] Cloning repository...
  🔍 [PM] Analyzing codebase structure...
  📝 [PM] Creating task breakdown...
  📢 [PM] Broadcasting tasks to agents...

Pane 1 (Backend):
  ⚙️  [Backend] Starting backend development...
  📨 [Backend] Waiting for task assignment...
  📝 [Backend] Received 2 tasks
  🔨 [Backend] Working on: Implement dark mode API endpoint...

Pane 2 (Frontend):
  🎨 [Frontend] Starting frontend development...
  📨 [Frontend] Waiting for task assignment...
  📝 [Frontend] Received 2 tasks
  🔨 [Frontend] Working on: Create theme toggle component...

Pane 3 (QA):
  🧪 [QA] Starting QA tasks...
  📨 [QA] Waiting for development completion...
  📝 [QA] Writing tests...
  🧪 [QA] Running tests...
  💾 [QA] Committing changes...
  🚀 [QA] Pushing to origin...
```

---

### Scene 5: The Result (1:30 - 1:50)
**Duration**: 20 seconds
**Visual**: GitHub interface or git log output

**Show**:
1. Git log showing the commit
2. GitHub branch (if possible, show the PR or diff)
3. Tests passing

**Script**:
> "And we're done. Four agents. Two minutes. One complete feature. With working tests, proper git history, and ready for code review. This is impossible with traditional single-agent systems."

**Technical Notes**:
- Show the actual GitHub commit in browser if possible
- Show `git log --oneline --graph` for nice visual
- Show test output if available

---

### Scene 6: The Closer (1:50 - 2:00)
**Duration**: 10 seconds
**Visual**: Final slide with project info

**Script**:
> "Claude Swarm plus E2B plus MCP Hub equals production-ready multi-agent coordination. Try it yourself at github.com/aspire11/claude-swarm."

**Show on screen**:
```
🤖 Claude Swarm
Multi-Agent Collaborative Development

✓ E2B Cloud Integration
✓ Docker MCP Hub Support
✓ Production-Ready Workflows

github.com/aspire11/claude-swarm
```

---

## Recording Tips

### Camera/Screen Setup
- **Terminal**:
  - Font: 16pt+ (readable in 1080p video)
  - Theme: Dark with good contrast
  - Shell prompt: Keep it clean and short

- **Recording Resolution**: 1920x1080 minimum

- **Frame Rate**: 30fps minimum

### Audio
- Use good microphone (not laptop mic)
- Record narration separately if needed
- Remove background noise
- Keep energy level high

### Editing
- Cut dead time (waiting for commands)
- Speed up boring parts (2x-4x)
- Add zoom effects on important moments
- Consider adding text overlays for clarity
- Add subtle background music (optional)

### What to Emphasize
1. **Speed**: "In seconds..." "Real-time..."
2. **Parallel execution**: "Simultaneously..." "At the same time..."
3. **Real tools**: "Actual GitHub repo..." "Production-ready..."
4. **Coordination**: "Agents communicate..." "Synchronized work..."

### What to Avoid
- Don't show errors or failures (practice until perfect)
- Don't waste time on setup
- Don't explain technical details (keep it high-level)
- Don't use jargon unless necessary

---

## Backup Plan

If live demo fails during recording:

**Plan A**: Pre-record the workflow execution
- Record the perfect run
- Use asciinema for terminal recording
- Edit in narration

**Plan B**: Use screenshots + diagrams
- Show architecture diagram
- Use annotated screenshots
- Show final GitHub commit

**Plan C**: Simplified demo
- Run with fewer agents (2 instead of 4)
- Use simpler task
- Show concept rather than full execution

---

## Post-Recording

- [ ] Watch full video
- [ ] Check audio sync
- [ ] Verify all text is readable
- [ ] Add captions if required
- [ ] Export in required format
- [ ] Test on different devices
- [ ] Get feedback from teammate
- [ ] Upload and submit!

---

## Example Alternative Scripts

### Version 2: More Technical
Focus on architecture and implementation details for technically-minded judges.

### Version 3: Business Value
Focus on use cases and ROI for non-technical judges.

### Version 4: Live Coding
Show creating a new workflow from scratch.

---

## Questions to Address (Optional FAQ)

If judges ask:

**Q: How is this different from LangGraph/CrewAI/AutoGPT?**
A: We focus on production deployment to cloud (E2B), real tool access (MCP), and true parallel execution. Most frameworks run locally and execute tasks sequentially.

**Q: What prevents agents from conflicting?**
A: Our messaging system includes task coordination, file locking, and synchronization primitives specifically designed for multi-agent workflows.

**Q: Can this scale to more agents?**
A: Absolutely. E2B sandboxes are isolated and can be deployed on-demand. We've tested with 10+ agents.

**Q: What about security?**
A: E2B provides isolated sandbox environments. MCPs run in controlled environments with proper authentication.

---

## Success Criteria

Your demo is successful if viewers can answer:
1. ✓ What is Claude Swarm? (Multi-agent coordination platform)
2. ✓ Why is it useful? (Collaborate on real coding tasks)
3. ✓ How does it work? (E2B + MCPs + Agent coordination)
4. ✓ Can I use it? (Yes, it's on GitHub)

Good luck! 🚀
