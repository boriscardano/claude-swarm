# Example Configuration Files

This directory contains ready-to-use configuration files for common Claude Swarm scenarios.

## Quick Start

Copy an example to your project root:

```bash
# For small teams (2-3 agents)
cp examples/configs/small-team.yaml .claudeswarm.yaml

# For large teams (10+ agents)
cp examples/configs/large-team.yaml .claudeswarm.yaml

# For fast-paced development
cp examples/configs/fast-paced.yaml .claudeswarm.yaml

# For security-critical projects
cp examples/configs/strict.yaml .claudeswarm.yaml
```

## Available Configurations

### default.yaml

Complete reference showing all configuration options with their default values.

**Use this when:**
- You want to see all available options
- You need a starting point for customization
- You want to understand the config structure

**Copy and customize:**
```bash
cp examples/configs/default.yaml .claudeswarm.yaml
# Edit as needed
```

---

### small-team.yaml

Optimized for 2-3 agents with close collaboration.

**Settings:**
- Higher message rate (15/min)
- Shorter lock timeout (3 minutes)
- Faster stale detection (45 seconds)
- Frequent auto-refresh (20 seconds)
- Auto-cleanup enabled

**Best for:**
- Small development teams
- Close-knit collaboration
- Quick iteration cycles
- Real-time coordination

```bash
cp examples/configs/small-team.yaml .claudeswarm.yaml
```

---

### large-team.yaml

Optimized for 10+ agents with structured coordination.

**Settings:**
- Lower message rate (8/min) to prevent flooding
- Longer lock timeout (10 minutes) for complex work
- Tolerates slower agents (90 seconds)
- Less frequent refresh (45 seconds)
- Custom onboarding messages for large teams

**Best for:**
- Large development teams
- Multiple sub-teams
- Complex projects
- Structured workflows

```bash
cp examples/configs/large-team.yaml .claudeswarm.yaml
```

---

### fast-paced.yaml

Optimized for rapid iteration and quick feedback.

**Settings:**
- Very high message rate (25/min)
- Very short lock timeout (2 minutes)
- Fast stale detection (30 seconds)
- Very frequent refresh (15 seconds)
- Auto-onboard enabled for speed

**Best for:**
- Hackathons
- Prototyping sessions
- Rapid development sprints
- Continuous deployment
- Time-sensitive projects

```bash
cp examples/configs/fast-paced.yaml .claudeswarm.yaml
```

---

### strict.yaml

Very conservative settings with manual controls.

**Settings:**
- Very low message rate (3/min)
- Very long lock timeout (30 minutes)
- No auto-cleanup (manual only)
- No auto-refresh (manual only)
- Detailed onboarding messages
- Manual onboarding only

**Best for:**
- Security-critical projects
- Regulated industries
- Mission-critical systems
- Training/learning environments
- Projects requiring audit trails

```bash
cp examples/configs/strict.yaml .claudeswarm.yaml
```

---

## Customizing Configurations

After copying a configuration file, you can:

1. **Edit with your preferred editor:**
   ```bash
   # Uses $EDITOR environment variable
   claudeswarm config edit
   ```

2. **View current settings:**
   ```bash
   claudeswarm config show
   ```

3. **Validate your changes:**
   ```bash
   claudeswarm config validate
   ```

## Configuration Options Reference

For complete documentation of all configuration options, see:
- [docs/CONFIGURATION.md](../../docs/CONFIGURATION.md) - Complete reference
- [docs/INTEGRATION_GUIDE.md](../../docs/INTEGRATION_GUIDE.md) - Integration guide
- [docs/TUTORIAL.md](../../docs/TUTORIAL.md) - Tutorial with config examples

## Key Configuration Areas

### Rate Limiting
Controls how many messages agents can send per minute.

**Adjust when:**
- Team size changes
- Message volume is too high/low
- Getting rate limit errors

### Locking
Controls file lock timeouts and cleanup behavior.

**Adjust when:**
- Locks timing out too quickly
- Too many stale locks
- Need longer edit sessions

### Discovery
Controls agent discovery and registry refresh.

**Adjust when:**
- Agents marked stale too quickly
- Need real-time discovery
- Performance issues with refresh

### Onboarding
Controls agent onboarding messages and behavior.

**Adjust when:**
- Need custom team instructions
- Want to auto-onboard new agents
- Different onboarding workflows

## Tips

1. **Start with an example** - Don't create from scratch
2. **Make small changes** - Test one setting at a time
3. **Validate often** - Run `claudeswarm config validate` after edits
4. **Commit to git** - Share team settings via version control
5. **Document changes** - Add comments explaining customizations

## Troubleshooting

### Configuration Not Found

```bash
$ claudeswarm config show
Configuration source: defaults (no config file found)
```

**Solution:** Copy an example or create new config:
```bash
claudeswarm config init
```

### Validation Errors

```bash
$ claudeswarm config validate
✗ Values: Invalid
  - rate_limiting.messages_per_minute must be > 0
```

**Solution:** Edit config and fix the error:
```bash
claudeswarm config edit
```

### Want to Reset to Defaults

```bash
# Backup current config
mv .claudeswarm.yaml .claudeswarm.yaml.backup

# Create fresh defaults
claudeswarm config init
```

## Support

- Full documentation: [docs/CONFIGURATION.md](../../docs/CONFIGURATION.md)
- Integration guide: [docs/INTEGRATION_GUIDE.md](../../docs/INTEGRATION_GUIDE.md)
- Tutorial: [docs/TUTORIAL.md](../../docs/TUTORIAL.md)
- Issues: [GitHub Issues](https://github.com/borisbanach/claude-swarm/issues)
