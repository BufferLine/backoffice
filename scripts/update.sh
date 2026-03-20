#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

echo "=== Updating Backoffice ==="

# Pull latest
echo "[1/4] Pulling latest code..."
git pull origin main

# Install backend deps
echo "[2/4] Installing backend dependencies..."
cd backend
source .venv/bin/activate
pip install -e "." -q
cd ..

# Run migrations
echo "[3/4] Running migrations..."
cd backend
source .venv/bin/activate
# Load production env if exists
if [ -f "$PROJECT_DIR/.env.production" ]; then
    set -a; source "$PROJECT_DIR/.env.production"; set +a
fi
alembic upgrade head
cd ..

# Restart service
echo "[4/4] Restarting service..."
PLIST_PATH="$HOME/Library/LaunchAgents/com.backoffice.server.plist"
if [ -f "$PLIST_PATH" ]; then
    launchctl unload "$PLIST_PATH" 2>/dev/null || true
    launchctl load "$PLIST_PATH"
    echo "Service restarted."
else
    echo "No launchd service found. Start manually."
fi

echo ""
echo "=== Update Complete ==="
