#!/bin/bash
# Reload claudeswarm CLI with latest changes
# Usage:
#   ./reload.sh         - Reload from local changes (default)
#   ./reload.sh local   - Reload from local changes
#   ./reload.sh github  - Reload from GitHub repository

set -e

# Get the script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Parse source argument
SOURCE="${1:-local}"

if [ "$SOURCE" != "local" ] && [ "$SOURCE" != "github" ]; then
    echo "❌ Invalid source: $SOURCE"
    echo ""
    echo "Usage:"
    echo "  ./reload.sh         - Reload from local changes (default)"
    echo "  ./reload.sh local   - Reload from local changes"
    echo "  ./reload.sh github  - Reload from GitHub repository"
    exit 1
fi

echo "🔄 Reloading claudeswarm CLI from $SOURCE..."
echo ""

# Step 1: Clear Python caches
echo "1️⃣  Clearing Python caches..."
find "$SCRIPT_DIR" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find "$SCRIPT_DIR" -type f -name "*.pyc" -delete 2>/dev/null || true
find /Library/Frameworks/Python.framework/Versions/3.12/lib/python3.12/site-packages -type d -name "__pycache__" -path "*/claudeswarm/*" -exec rm -rf {} + 2>/dev/null || true
echo "   ✓ Caches cleared"
echo ""

# Step 2: Install from source
echo "2️⃣  Installing from $SOURCE..."
if [ "$SOURCE" = "local" ]; then
    uv tool install --force --editable "$SCRIPT_DIR" > /dev/null 2>&1
    echo "   ✓ Installed from local directory (editable mode)"
else
    uv tool install --force git+https://github.com/boriscardano/claude-swarm.git > /dev/null 2>&1
    echo "   ✓ Installed from GitHub"
fi
echo ""

# Step 3: Verify installation
echo "3️⃣  Verifying installation..."
VERSION=$(python3 -c "import claudeswarm; print(claudeswarm.__version__)" 2>/dev/null || echo "unknown")
echo "   ✓ Version: $VERSION"
if [ "$SOURCE" = "local" ]; then
    echo "   ✓ Editable location: $SCRIPT_DIR"
fi
echo ""

echo "✅ Reload complete!"
echo ""
if [ "$SOURCE" = "local" ]; then
    echo "You can now use 'claudeswarm' with your latest LOCAL changes in any tmux pane."
    echo "Changes you make to the code will be immediately available."
else
    echo "You can now use 'claudeswarm' with the latest GITHUB version in any tmux pane."
fi
echo ""
echo "Quick test: claudeswarm discover-agents"
