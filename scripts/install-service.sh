#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Create launchd plist
PLIST_PATH="$HOME/Library/LaunchAgents/com.bufferline.backoffice.plist"

cat > "$PLIST_PATH" << PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.bufferline.backoffice</string>
    <key>ProgramArguments</key>
    <array>
        <string>${PROJECT_DIR}/backend/.venv/bin/uvicorn</string>
        <string>app.main:app</string>
        <string>--host</string>
        <string>127.0.0.1</string>
        <string>--port</string>
        <string>8000</string>
    </array>
    <key>WorkingDirectory</key>
    <string>${PROJECT_DIR}/backend</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>${PROJECT_DIR}/backend/.venv/bin:/usr/local/bin:/usr/bin:/bin</string>
    </dict>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>${PROJECT_DIR}/logs/backoffice.log</string>
    <key>StandardErrorPath</key>
    <string>${PROJECT_DIR}/logs/backoffice.error.log</string>
</dict>
</plist>
PLIST

# Load env vars into plist
if [ -f "$PROJECT_DIR/.env.production" ]; then
    # Read env file and add to plist EnvironmentVariables
    echo "Note: Set environment variables in the plist manually or use an env wrapper."
fi

mkdir -p "$PROJECT_DIR/logs"

echo "Service plist created at: $PLIST_PATH"
echo ""
echo "To start:  launchctl load $PLIST_PATH"
echo "To stop:   launchctl unload $PLIST_PATH"
echo "To restart: launchctl unload $PLIST_PATH && launchctl load $PLIST_PATH"
echo "Logs at:   $PROJECT_DIR/logs/"
