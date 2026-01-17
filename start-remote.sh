#!/bin/bash
#
# Start the Expo Dev MCP server with ngrok for remote access
#
# Prerequisites:
#   - ngrok installed: brew install ngrok
#   - ngrok authenticated: ngrok config add-authtoken YOUR_TOKEN
#   - tunneld running: sudo python3 -m pymobiledevice3 remote tunneld
#
# Usage:
#   ./start-remote.sh
#   ./start-remote.sh --port 9000
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PORT="${1:-8080}"

# Check for ngrok
if ! command -v ngrok &> /dev/null; then
    echo "Error: ngrok is not installed."
    echo "Install with: brew install ngrok"
    echo "Then authenticate: ngrok config add-authtoken YOUR_TOKEN"
    exit 1
fi

# Activate venv
if [ -f "$SCRIPT_DIR/.venv/bin/activate" ]; then
    source "$SCRIPT_DIR/.venv/bin/activate"
else
    echo "Error: Virtual environment not found."
    echo "Run: python3 -m venv .venv && source .venv/bin/activate && pip install -e ."
    exit 1
fi

# Generate auth token
AUTH_TOKEN=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")

# Start ngrok in background
echo "Starting ngrok on port $PORT..."
ngrok http $PORT --log=stdout > /tmp/ngrok.log 2>&1 &
NGROK_PID=$!

# Wait for ngrok to start and get URL
sleep 2
NGROK_URL=$(curl -s http://localhost:4040/api/tunnels | python3 -c "import sys, json; print(json.load(sys.stdin)['tunnels'][0]['public_url'])" 2>/dev/null || echo "")

if [ -z "$NGROK_URL" ]; then
    echo "Error: Failed to get ngrok URL. Check if ngrok is authenticated."
    echo "Run: ngrok config add-authtoken YOUR_TOKEN"
    kill $NGROK_PID 2>/dev/null
    exit 1
fi

# Cleanup on exit
cleanup() {
    echo ""
    echo "Shutting down..."
    kill $NGROK_PID 2>/dev/null
    exit 0
}
trap cleanup SIGINT SIGTERM

# Print connection info
echo ""
echo "============================================================"
echo "  Expo Dev MCP Server - Remote Access Ready"
echo "============================================================"
echo ""
echo "  ngrok URL: $NGROK_URL"
echo "  Auth Token: $AUTH_TOKEN"
echo ""
echo "------------------------------------------------------------"
echo "  Claude Configuration:"
echo "------------------------------------------------------------"
echo ""
echo '  {'
echo '    "mcpServers": {'
echo '      "expo-dev": {'
echo '        "type": "sse",'
echo "        \"url\": \"$NGROK_URL/sse\","
echo '        "headers": {'
echo "          \"Authorization\": \"Bearer $AUTH_TOKEN\""
echo '        }'
echo '      }'
echo '    }'
echo '  }'
echo ""
echo "============================================================"
echo ""
echo "Press Ctrl+C to stop"
echo ""

# Start the MCP server
python -m expo_dev_mcp.server --http --port $PORT --token "$AUTH_TOKEN"
