#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

echo "=== Backoffice Production Setup ==="
echo ""

# Check prerequisites
command -v python3 >/dev/null || { echo "Error: python3 not found"; exit 1; }
command -v cloudflared >/dev/null || { echo "Warning: cloudflared not found. Install it for tunnel support."; }

# Create venv
echo "[1/5] Setting up Python environment..."
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -e "." -q
cd ..

# Install CLI
echo "[2/5] Installing CLI..."
cd cli
pip install -e "." -q
cd ..

# Check for production env
echo "[3/5] Checking environment..."
if [ ! -f .env.production ]; then
    cp .env.production.example .env.production
    echo "Created .env.production from template."
    echo ">>> EDIT .env.production with your Supabase/Cloudflare settings <<<"
    echo ""
fi

# Run migrations
echo "[4/5] Running migrations..."
cd backend
source .venv/bin/activate
set -a; source "$PROJECT_DIR/.env.production"; set +a
alembic upgrade head
cd ..

# Install launchd service
echo "[5/5] Installing service..."
scripts/install-service.sh

echo ""
echo "=== Setup Complete ==="
echo ""
echo "Next steps:"
echo "  1. Edit .env.production with your database and storage URLs"
echo "  2. Run: acct init --company-name 'Your Company' --admin-email you@example.com --admin-password 'xxx' --api-url https://your-domain.com"
echo "  3. Start service: launchctl load ~/Library/LaunchAgents/com.backoffice.server.plist"
echo "  4. Set up Cloudflare Tunnel: cloudflared tunnel --url http://localhost:8000"
