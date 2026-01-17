# Expo Dev Build MCP Server

An MCP server that lets Claude see and interact with iOS devices running Expo development builds. Take screenshots, view logs, launch apps, and debug your mobile app through conversation.

## What It Does

```
┌─────────────────┐                    ┌─────────────────┐                    ┌─────────────────┐
│  Claude Code    │ ◄── MCP Protocol ──►  This Server    │ ◄── USB/Tunnel ──► │  Your iPhone    │
│  or Desktop     │                    │  (Python)       │                    │  (Expo App)     │
└─────────────────┘                    └─────────────────┘                    └─────────────────┘
```

**Available Tools:**
- `screenshot` - Capture the device screen (Claude can see and analyze it)
- `get_logs` - Stream system logs for debugging
- `list_apps` - See installed applications
- `launch_app` - Start an app by bundle ID
- `kill_app` - Force quit an app
- `device_info` - Get model, iOS version, battery, etc.
- `list_devices` - Find connected iOS devices

## Quick Start

### 1. Prerequisites

| Requirement | How to Check |
|-------------|--------------|
| macOS | Required (iOS tools only work on Mac) |
| Python 3.10+ | `python3 --version` (install via `brew install python@3.12` if needed) |
| Homebrew | `brew --version` (install from https://brew.sh if needed) |
| iOS device | Physical iPhone/iPad connected via USB |

### 2. Clone and Install

```bash
git clone https://github.com/YOUR_USERNAME/expo-dev-build-mcp.git
cd expo-dev-build-mcp

# Create virtual environment with Python 3.10+
python3 -m venv .venv
source .venv/bin/activate

# Upgrade pip and install
pip install --upgrade pip
pip install -e .
```

### 3. Prepare Your iOS Device

**Connect and trust:**
1. Connect your iPhone/iPad via USB cable
2. If prompted on the device, tap "Trust This Computer"
3. Verify connection: `python3 -m pymobiledevice3 usbmux list`

**Enable Developer Mode (iOS 16+):**
1. Open Xcode on your Mac and connect your device (this registers it as a developer device)
2. On your iPhone: **Settings → Privacy & Security → Developer Mode → Enable**
3. Restart when prompted

### 4. Start the Tunnel Daemon (iOS 17+ Required)

iOS 17+ requires a tunnel daemon for developer commands. **Run this in a separate terminal and keep it running:**

```bash
cd expo-dev-build-mcp
source .venv/bin/activate
sudo python3 -m pymobiledevice3 remote tunneld
```

Enter your Mac password when prompted. You'll see connection logs when it's working.

> **Tip:** Keep this terminal open while using the MCP server. You can also set this up as a launchd service for automatic startup.

### 5. Test It Works

In a new terminal:

```bash
cd expo-dev-build-mcp
source .venv/bin/activate

# List devices
python3 -m pymobiledevice3 usbmux list

# Take a test screenshot
python3 -m pymobiledevice3 developer dvt screenshot test.png
open test.png
```

If the screenshot opens, you're ready to configure Claude.

### 6. Configure Claude

**For Claude Code**, add to your MCP settings (run `claude mcp` to find config location):

```json
{
  "mcpServers": {
    "expo-dev": {
      "command": "/ABSOLUTE/PATH/TO/expo-dev-build-mcp/.venv/bin/python",
      "args": ["-m", "expo_dev_mcp.server"]
    }
  }
}
```

**For Claude Desktop**, add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "expo-dev": {
      "command": "/ABSOLUTE/PATH/TO/expo-dev-build-mcp/.venv/bin/python",
      "args": ["-m", "expo_dev_mcp.server"]
    }
  }
}
```

> **Important:** Replace `/ABSOLUTE/PATH/TO/` with the actual path. Find it with `pwd` in the project directory.

Restart Claude Code/Desktop after updating the config.

## Usage

Once configured, ask Claude things like:

- "Take a screenshot of my phone"
- "What's on my iPhone screen?"
- "Show me the device logs"
- "What apps are installed?"
- "Launch com.mycompany.myexpoapp"
- "Kill the app and relaunch it"

Claude will use the MCP tools automatically and can see/analyze the screenshots.

## Troubleshooting

### "No device found"
- Check USB connection
- Run `python3 -m pymobiledevice3 usbmux list` - device should appear
- If not listed, try a different USB cable or port
- Make sure you tapped "Trust" on the device

### "InvalidServiceError" or "Unable to connect to Tunneld"
- **iOS 17+ requires the tunnel daemon running**
- Start it in a separate terminal: `sudo python3 -m pymobiledevice3 remote tunneld`
- Keep that terminal open while using the MCP server

### "Failed to take screenshot"
- Ensure Developer Mode is enabled (Settings → Privacy & Security → Developer Mode)
- Make sure tunneld is running (for iOS 17+)
- Try: `python3 -m pymobiledevice3 developer dvt screenshot test.png`

### Screenshot works manually but not via MCP
- Check the path in your Claude config is correct (must be absolute path)
- Restart Claude Code/Desktop after config changes
- Check MCP server is loaded: run `claude mcp` in Claude Code

### "sudo: a password is required"
- The tunneld command needs sudo for network permissions
- Run it in a regular terminal (not via script) so you can enter your password

## How It Works

This server uses [pymobiledevice3](https://github.com/doronz88/pymobiledevice3), a Python library that implements Apple's proprietary protocols for communicating with iOS devices:

- **usbmuxd** - USB multiplexing (multiple services over one USB connection)
- **Lockdown** - Device pairing and service discovery
- **DVT (Developer Tools)** - Screenshots, process control, instrumentation

No jailbreak required. It uses the same protocols as Xcode.

## Project Structure

```
expo-dev-build-mcp/
├── pyproject.toml           # Package configuration
├── README.md                # This file
└── src/
    └── expo_dev_mcp/
        ├── __init__.py
        └── server.py        # MCP server implementation
```

## Development

```bash
# Install in development mode
pip install -e .

# Run server directly (for testing)
python -m expo_dev_mcp.server

# Test with MCP Inspector
npx @modelcontextprotocol/inspector python -m expo_dev_mcp.server
```

## Future: Gesture Support (Phase 2)

This MVP is view-only. Phase 2 would add tap/swipe gestures via WebDriverAgent, requiring:
- Apple Developer account (paid)
- Code signing and provisioning profiles
- WebDriverAgent installed on device

See the project research notes for implementation details.

## License

MIT
