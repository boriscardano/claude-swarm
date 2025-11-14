.PHONY: help install reload reload-local reload-github clean test discover onboard dashboard

help:
	@echo "Claude Swarm Development Commands"
	@echo ""
	@echo "  make install        - Install claudeswarm in editable mode"
	@echo "  make reload         - Reload claudeswarm with latest LOCAL changes (default)"
	@echo "  make reload-local   - Reload claudeswarm with latest LOCAL changes"
	@echo "  make reload-github  - Reload claudeswarm from GitHub repository"
	@echo "  make clean          - Clean Python caches and build artifacts"
	@echo "  make discover       - Discover active agents"
	@echo "  make onboard        - Onboard all agents"
	@echo "  make dashboard      - Start web dashboard"
	@echo "  make test           - Run tests (when available)"

install:
	@echo "Installing claudeswarm in editable mode..."
	@uv tool install --force --editable .
	@echo "✓ Installation complete"

reload: reload-local

reload-local:
	@./reload.sh local

reload-github:
	@./reload.sh github

clean:
	@echo "Cleaning Python caches and build artifacts..."
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" -delete 2>/dev/null || true
	@find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name "build" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name "dist" -exec rm -rf {} + 2>/dev/null || true
	@echo "✓ Cleanup complete"

discover:
	@claudeswarm discover-agents

onboard:
	@claudeswarm onboard

dashboard:
	@claudeswarm start-dashboard

test:
	@echo "Tests not yet implemented"
	@echo "TODO: Add pytest configuration"
