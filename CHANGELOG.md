# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Cross-Project Coordination Configuration**: Added `enable_cross_project_coordination` flag to `DiscoveryConfig` for controlling agent discovery scope
  - Default: `false` (project-isolated swarms for security)
  - When `true`: Agents from all projects are visible for cross-project coordination
  - Configuration option available in both YAML and TOML formats

### Changed
- **Agent Discovery Behavior**: Agent discovery now respects the `enable_cross_project_coordination` configuration flag
  - By default, agents are isolated to their project directory (backward compatible)
  - Opt-in to cross-project coordination by setting `discovery.enable_cross_project_coordination: true`

### Security
- **Project Isolation by Default**: Agent discovery is now project-scoped by default to prevent unintended cross-project access
  - Previous behavior allowed all agents to see each other regardless of project
  - New default behavior isolates agents to their project directory
  - Users who need cross-project coordination must explicitly opt-in via configuration

## Migration Guide

### For Existing Users

If you were relying on cross-project agent discovery (agents from different projects seeing each other), you need to explicitly enable this feature:

**YAML Configuration (.claudeswarm.yaml):**
```yaml
discovery:
  enable_cross_project_coordination: true
```

**TOML Configuration (.claudeswarm.toml):**
```toml
[discovery]
enable_cross_project_coordination = true
```

### Security Considerations

Before enabling cross-project coordination, consider:

1. **Multi-tenant Environments**: In shared environments, cross-project coordination may expose agent information across project boundaries
2. **Sensitive Projects**: Projects with sensitive data should keep the default isolation
3. **Development Workflows**: Most single-developer workflows work fine with project isolation
4. **Team Coordination**: Teams working across multiple related projects may benefit from cross-project coordination

### Default Behavior

With no configuration (or `enable_cross_project_coordination: false`):
- Agents only discover other agents in the same project directory
- Each project has its own isolated swarm
- More secure for multi-project environments

With `enable_cross_project_coordination: true`:
- Agents discover all Claude Code agents system-wide
- Enables coordination across different projects
- Use with caution in shared or multi-tenant environments
