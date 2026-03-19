#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

echo "=== Stopping Backoffice Services ==="

pkill -f "uvicorn app.main" 2>/dev/null && echo "Stopped uvicorn." || echo "uvicorn was not running."
docker compose down 2>/dev/null && echo "Stopped Docker services." || echo "Docker services were not running."

echo "All services stopped."
