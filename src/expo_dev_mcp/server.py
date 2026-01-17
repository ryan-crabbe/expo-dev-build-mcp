"""
Expo Dev Build MCP Server

An MCP server for interacting with iOS devices running Expo development builds.
Provides tools for screenshots, logs, device info, and app management.

Supports two transport modes:
- stdio (default): For local Claude Desktop/Code integration
- http: For remote access via ngrok tunnel
"""

import argparse
import asyncio
import base64
import json
import os
import secrets
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import (
    TextContent,
    ImageContent,
    Tool,
)


# Auth token for HTTP mode
_auth_token: str | None = None


def _run_pymobiledevice3_cmd(args: list[str], timeout: int = 30) -> tuple[bool, str]:
    """Run a pymobiledevice3 CLI command and return (success, output)."""
    try:
        result = subprocess.run(
            ["python3", "-m", "pymobiledevice3"] + args,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode == 0:
            return True, result.stdout
        else:
            return False, result.stderr or result.stdout
    except subprocess.TimeoutExpired:
        return False, f"Command timed out after {timeout} seconds"
    except FileNotFoundError:
        return False, "pymobiledevice3 not found. Install with: pip install pymobiledevice3"
    except Exception as e:
        return False, str(e)


def _get_connected_devices() -> list[dict[str, Any]]:
    """Get list of connected iOS devices."""
    success, output = _run_pymobiledevice3_cmd(["usbmux", "list", "--no-color", "-o", "json"])
    if not success:
        return []

    try:
        devices = json.loads(output)
        return devices if isinstance(devices, list) else []
    except json.JSONDecodeError:
        return []


def _get_device_identifier(device_id: str | None) -> str | None:
    """Get device UDID, using first device if none specified."""
    devices = _get_connected_devices()
    if not devices:
        return None

    if device_id:
        for device in devices:
            if device.get("UniqueDeviceID") == device_id or device.get("DeviceName") == device_id:
                return device.get("UniqueDeviceID")
        return None

    # Return first device if none specified
    return devices[0].get("UniqueDeviceID")


# Create the MCP server
server = Server("expo-dev-mcp")


@server.list_tools()
async def list_tools() -> list[Tool]:
    """List available tools."""
    return [
        Tool(
            name="list_devices",
            description="List all connected iOS devices. Returns device names, UDIDs, and connection info.",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": [],
            },
        ),
        Tool(
            name="device_info",
            description="Get detailed information about a connected iOS device including model, iOS version, battery, storage, etc.",
            inputSchema={
                "type": "object",
                "properties": {
                    "device_id": {
                        "type": "string",
                        "description": "Device UDID or name. If not provided, uses the first connected device.",
                    },
                },
                "required": [],
            },
        ),
        Tool(
            name="screenshot",
            description="Take a screenshot of the iOS device screen. Returns the image that can be viewed directly.",
            inputSchema={
                "type": "object",
                "properties": {
                    "device_id": {
                        "type": "string",
                        "description": "Device UDID or name. If not provided, uses the first connected device.",
                    },
                },
                "required": [],
            },
        ),
        Tool(
            name="get_logs",
            description="Get recent system logs from the iOS device. Useful for debugging app crashes and issues.",
            inputSchema={
                "type": "object",
                "properties": {
                    "device_id": {
                        "type": "string",
                        "description": "Device UDID or name. If not provided, uses the first connected device.",
                    },
                    "duration_seconds": {
                        "type": "integer",
                        "description": "How many seconds of logs to capture. Default is 5 seconds.",
                        "default": 5,
                    },
                    "filter": {
                        "type": "string",
                        "description": "Optional text filter to only show logs containing this string.",
                    },
                },
                "required": [],
            },
        ),
        Tool(
            name="list_apps",
            description="List all installed applications on the iOS device.",
            inputSchema={
                "type": "object",
                "properties": {
                    "device_id": {
                        "type": "string",
                        "description": "Device UDID or name. If not provided, uses the first connected device.",
                    },
                    "filter": {
                        "type": "string",
                        "description": "Optional filter to search for specific apps by name or bundle ID.",
                    },
                },
                "required": [],
            },
        ),
        Tool(
            name="launch_app",
            description="Launch an application on the iOS device by its bundle ID.",
            inputSchema={
                "type": "object",
                "properties": {
                    "bundle_id": {
                        "type": "string",
                        "description": "The bundle identifier of the app to launch (e.g., 'com.example.myapp').",
                    },
                    "device_id": {
                        "type": "string",
                        "description": "Device UDID or name. If not provided, uses the first connected device.",
                    },
                },
                "required": ["bundle_id"],
            },
        ),
        Tool(
            name="kill_app",
            description="Force quit an application on the iOS device.",
            inputSchema={
                "type": "object",
                "properties": {
                    "bundle_id": {
                        "type": "string",
                        "description": "The bundle identifier of the app to kill.",
                    },
                    "device_id": {
                        "type": "string",
                        "description": "Device UDID or name. If not provided, uses the first connected device.",
                    },
                },
                "required": ["bundle_id"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent | ImageContent]:
    """Handle tool calls."""

    if name == "list_devices":
        return await handle_list_devices()
    elif name == "device_info":
        return await handle_device_info(arguments.get("device_id"))
    elif name == "screenshot":
        return await handle_screenshot(arguments.get("device_id"))
    elif name == "get_logs":
        return await handle_get_logs(
            arguments.get("device_id"),
            arguments.get("duration_seconds", 5),
            arguments.get("filter"),
        )
    elif name == "list_apps":
        return await handle_list_apps(
            arguments.get("device_id"),
            arguments.get("filter"),
        )
    elif name == "launch_app":
        return await handle_launch_app(
            arguments["bundle_id"],
            arguments.get("device_id"),
        )
    elif name == "kill_app":
        return await handle_kill_app(
            arguments["bundle_id"],
            arguments.get("device_id"),
        )
    else:
        return [TextContent(type="text", text=f"Unknown tool: {name}")]


async def handle_list_devices() -> list[TextContent]:
    """List connected iOS devices."""
    devices = _get_connected_devices()

    if not devices:
        return [TextContent(
            type="text",
            text="No iOS devices connected.\n\nMake sure:\n1. Your device is connected via USB\n2. You've trusted the computer on your device\n3. pymobiledevice3 is installed: pip install pymobiledevice3",
        )]

    lines = [f"Found {len(devices)} connected device(s):\n"]
    for i, device in enumerate(devices, 1):
        lines.append(f"{i}. {device.get('DeviceName', 'Unknown')}")
        lines.append(f"   UDID: {device.get('UniqueDeviceID', 'Unknown')}")
        lines.append(f"   Connection: {device.get('ConnectionType', 'Unknown')}")
        lines.append("")

    return [TextContent(type="text", text="\n".join(lines))]


async def handle_device_info(device_id: str | None) -> list[TextContent]:
    """Get detailed device information."""
    udid = _get_device_identifier(device_id)
    if not udid:
        return [TextContent(type="text", text="No device found. Connect an iOS device and try again.")]

    # Get device info using pymobiledevice3
    args = ["lockdown", "info", "--udid", udid, "-o", "json"]
    success, output = _run_pymobiledevice3_cmd(args)

    if not success:
        return [TextContent(type="text", text=f"Failed to get device info: {output}")]

    try:
        info = json.loads(output)
    except json.JSONDecodeError:
        return [TextContent(type="text", text=f"Failed to parse device info: {output}")]

    # Format key information
    lines = [
        f"Device: {info.get('DeviceName', 'Unknown')}",
        f"Model: {info.get('ProductType', 'Unknown')} ({info.get('HardwareModel', '')})",
        f"iOS Version: {info.get('ProductVersion', 'Unknown')} (Build {info.get('BuildVersion', '')})",
        f"UDID: {info.get('UniqueDeviceID', 'Unknown')}",
        f"Serial: {info.get('SerialNumber', 'Unknown')}",
        f"WiFi MAC: {info.get('WiFiAddress', 'Unknown')}",
        f"Bluetooth MAC: {info.get('BluetoothAddress', 'Unknown')}",
        "",
        f"Device Class: {info.get('DeviceClass', 'Unknown')}",
        f"CPU: {info.get('CPUArchitecture', 'Unknown')}",
        f"Supports 5G: {info.get('Supports5GStandalone', 'Unknown')}",
    ]

    # Add battery info if available
    if "BatteryCurrentCapacity" in info:
        lines.append(f"Battery: {info.get('BatteryCurrentCapacity', '?')}%")

    return [TextContent(type="text", text="\n".join(lines))]


async def handle_screenshot(device_id: str | None) -> list[TextContent | ImageContent]:
    """Take a screenshot of the device."""
    udid = _get_device_identifier(device_id)
    if not udid:
        return [TextContent(type="text", text="No device found. Connect an iOS device and try again.")]

    # Create a temporary file for the screenshot
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        # Take screenshot using pymobiledevice3
        args = ["developer", "dvt", "screenshot", tmp_path, "--udid", udid]
        success, output = _run_pymobiledevice3_cmd(args, timeout=60)

        if not success:
            return [TextContent(
                type="text",
                text=f"Failed to take screenshot: {output}\n\nNote: Screenshots require Developer Mode to be enabled on iOS 16+ devices.",
            )]

        # Read and encode the image
        screenshot_path = Path(tmp_path)
        if not screenshot_path.exists():
            return [TextContent(type="text", text="Screenshot file was not created.")]

        image_data = screenshot_path.read_bytes()
        base64_image = base64.standard_b64encode(image_data).decode("utf-8")

        return [
            ImageContent(
                type="image",
                data=base64_image,
                mimeType="image/png",
            ),
            TextContent(
                type="text",
                text=f"Screenshot captured at {datetime.now().strftime('%H:%M:%S')}",
            ),
        ]
    finally:
        # Clean up temp file
        try:
            Path(tmp_path).unlink()
        except Exception:
            pass


async def handle_get_logs(
    device_id: str | None,
    duration_seconds: int,
    filter_text: str | None,
) -> list[TextContent]:
    """Get device logs."""
    udid = _get_device_identifier(device_id)
    if not udid:
        return [TextContent(type="text", text="No device found. Connect an iOS device and try again.")]

    duration_seconds = min(max(duration_seconds, 1), 30)  # Clamp between 1-30 seconds

    # Use syslog to capture logs
    args = ["python3", "-m", "pymobiledevice3", "syslog", "live", "--udid", udid, "--no-color"]

    try:
        process = subprocess.Popen(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        # Collect logs for the specified duration
        logs = []
        start_time = asyncio.get_event_loop().time()

        while asyncio.get_event_loop().time() - start_time < duration_seconds:
            if process.poll() is not None:
                break

            # Non-blocking read with small timeout
            import select
            if select.select([process.stdout], [], [], 0.1)[0]:
                line = process.stdout.readline()
                if line:
                    # Apply filter if specified
                    if filter_text is None or filter_text.lower() in line.lower():
                        logs.append(line.rstrip())

            await asyncio.sleep(0.05)

        process.terminate()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()

        if not logs:
            msg = f"No logs captured in {duration_seconds} seconds."
            if filter_text:
                msg += f" (filter: '{filter_text}')"
            return [TextContent(type="text", text=msg)]

        # Limit output to last 100 lines
        if len(logs) > 100:
            logs = logs[-100:]
            header = f"Showing last 100 of {len(logs)} log lines:\n\n"
        else:
            header = f"Captured {len(logs)} log lines:\n\n"

        return [TextContent(type="text", text=header + "\n".join(logs))]

    except Exception as e:
        return [TextContent(type="text", text=f"Failed to capture logs: {e}")]


async def handle_list_apps(device_id: str | None, filter_text: str | None) -> list[TextContent]:
    """List installed apps."""
    udid = _get_device_identifier(device_id)
    if not udid:
        return [TextContent(type="text", text="No device found. Connect an iOS device and try again.")]

    args = ["apps", "list", "--udid", udid, "-o", "json"]
    success, output = _run_pymobiledevice3_cmd(args, timeout=60)

    if not success:
        return [TextContent(type="text", text=f"Failed to list apps: {output}")]

    try:
        apps = json.loads(output)
    except json.JSONDecodeError:
        return [TextContent(type="text", text=f"Failed to parse app list: {output}")]

    # Format app list
    lines = []
    for bundle_id, app_info in sorted(apps.items()):
        name = app_info.get("CFBundleDisplayName") or app_info.get("CFBundleName", bundle_id)
        version = app_info.get("CFBundleShortVersionString", "")

        # Apply filter
        if filter_text:
            search_text = f"{name} {bundle_id}".lower()
            if filter_text.lower() not in search_text:
                continue

        lines.append(f"• {name}")
        lines.append(f"  Bundle ID: {bundle_id}")
        if version:
            lines.append(f"  Version: {version}")
        lines.append("")

    if not lines:
        if filter_text:
            return [TextContent(type="text", text=f"No apps found matching '{filter_text}'.")]
        return [TextContent(type="text", text="No apps found.")]

    header = f"Found {len(lines) // 3} app(s)"
    if filter_text:
        header += f" matching '{filter_text}'"
    header += ":\n\n"

    return [TextContent(type="text", text=header + "\n".join(lines))]


async def handle_launch_app(bundle_id: str, device_id: str | None) -> list[TextContent]:
    """Launch an app on the device."""
    udid = _get_device_identifier(device_id)
    if not udid:
        return [TextContent(type="text", text="No device found. Connect an iOS device and try again.")]

    args = ["developer", "dvt", "launch", bundle_id, "--udid", udid]
    success, output = _run_pymobiledevice3_cmd(args, timeout=30)

    if not success:
        return [TextContent(
            type="text",
            text=f"Failed to launch {bundle_id}: {output}\n\nMake sure the app is installed and Developer Mode is enabled.",
        )]

    return [TextContent(type="text", text=f"Launched {bundle_id}")]


async def handle_kill_app(bundle_id: str, device_id: str | None) -> list[TextContent]:
    """Kill an app on the device."""
    udid = _get_device_identifier(device_id)
    if not udid:
        return [TextContent(type="text", text="No device found. Connect an iOS device and try again.")]

    args = ["developer", "dvt", "kill", bundle_id, "--udid", udid]
    success, output = _run_pymobiledevice3_cmd(args, timeout=30)

    if not success:
        return [TextContent(type="text", text=f"Failed to kill {bundle_id}: {output}")]

    return [TextContent(type="text", text=f"Killed {bundle_id}")]


# =============================================================================
# Transport: stdio (default, for local use)
# =============================================================================

async def run_stdio_server():
    """Run the MCP server with stdio transport (local use)."""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


# =============================================================================
# Transport: HTTP with SSE (for remote use via ngrok)
# =============================================================================

def create_http_app(auth_token: str):
    """Create a Starlette app for HTTP transport with auth."""
    from starlette.applications import Starlette
    from starlette.middleware import Middleware
    from starlette.middleware.cors import CORSMiddleware
    from starlette.requests import Request
    from starlette.responses import JSONResponse, Response
    from starlette.routing import Route
    from mcp.server.sse import SseServerTransport

    # Create SSE transport
    sse = SseServerTransport("/messages/")

    async def handle_sse(request: Request):
        """Handle SSE connections for MCP."""
        # Check auth
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return JSONResponse({"error": "Missing Bearer token"}, status_code=401)

        token = auth_header[7:]  # Remove "Bearer " prefix
        if token != auth_token:
            return JSONResponse({"error": "Invalid token"}, status_code=403)

        async with sse.connect_sse(
            request.scope, request.receive, request._send
        ) as streams:
            await server.run(
                streams[0],
                streams[1],
                server.create_initialization_options(),
            )
        return Response()

    async def handle_messages(request: Request):
        """Handle POST messages for MCP."""
        # Check auth
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return JSONResponse({"error": "Missing Bearer token"}, status_code=401)

        token = auth_header[7:]
        if token != auth_token:
            return JSONResponse({"error": "Invalid token"}, status_code=403)

        await sse.handle_post_message(request.scope, request.receive, request._send)
        return Response()

    async def health_check(request: Request):
        """Health check endpoint (no auth required)."""
        return JSONResponse({
            "status": "ok",
            "server": "expo-dev-mcp",
            "transport": "http+sse",
        })

    routes = [
        Route("/health", health_check, methods=["GET"]),
        Route("/sse", handle_sse, methods=["GET"]),
        Route("/messages/", handle_messages, methods=["POST"]),
    ]

    middleware = [
        Middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_methods=["*"],
            allow_headers=["*"],
        )
    ]

    return Starlette(routes=routes, middleware=middleware)


async def run_http_server(port: int, auth_token: str):
    """Run the MCP server with HTTP transport."""
    import uvicorn

    app = create_http_app(auth_token)

    config = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=port,
        log_level="warning",
    )
    server_instance = uvicorn.Server(config)
    await server_instance.serve()


# =============================================================================
# Main entry point
# =============================================================================

def main():
    """Main entry point with CLI argument parsing."""
    parser = argparse.ArgumentParser(
        description="Expo Dev Build MCP Server",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run locally (stdio mode, default)
  python -m expo_dev_mcp.server

  # Run in HTTP mode for remote access
  python -m expo_dev_mcp.server --http --port 8080

  # Run with ngrok (in another terminal: ngrok http 8080)
  python -m expo_dev_mcp.server --http --port 8080
        """
    )

    parser.add_argument(
        "--http",
        action="store_true",
        help="Run in HTTP mode instead of stdio (for remote access via ngrok)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Port for HTTP server (default: 8080)",
    )
    parser.add_argument(
        "--token",
        type=str,
        default=None,
        help="Auth token for HTTP mode (auto-generated if not provided)",
    )

    args = parser.parse_args()

    if args.http:
        # HTTP mode with auth
        auth_token = args.token or secrets.token_urlsafe(32)

        print("=" * 60, file=sys.stderr)
        print("Expo Dev Build MCP Server (HTTP Mode)", file=sys.stderr)
        print("=" * 60, file=sys.stderr)
        print(f"\nServer running on http://0.0.0.0:{args.port}", file=sys.stderr)
        print(f"\nAuth Token: {auth_token}", file=sys.stderr)
        print("\n" + "-" * 60, file=sys.stderr)
        print("To expose via ngrok, run in another terminal:", file=sys.stderr)
        print(f"  ngrok http {args.port}", file=sys.stderr)
        print("\nThen configure Claude with the ngrok URL:", file=sys.stderr)
        print("""
{
  "mcpServers": {
    "expo-dev": {
      "type": "sse",
      "url": "https://YOUR-NGROK-URL/sse",
      "headers": {
        "Authorization": "Bearer YOUR_TOKEN"
      }
    }
  }
}
""", file=sys.stderr)
        print("-" * 60, file=sys.stderr)
        print(f"\nReplace YOUR_TOKEN with: {auth_token}", file=sys.stderr)
        print("=" * 60, file=sys.stderr)

        asyncio.run(run_http_server(args.port, auth_token))
    else:
        # Default stdio mode
        asyncio.run(run_stdio_server())


if __name__ == "__main__":
    main()
