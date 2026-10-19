"""Mock File Manager MCP Server for testing and demo."""

from __future__ import annotations

import argparse
import json

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

mcp = MCPServer("FileManager", instructions="A mock file manager for testing the gateway.")

# Fake filesystem
MOCK_FS: dict[str, str] = {
    "/docs/readme.txt": "Welcome to AgentGateWay!",
    "/docs/architecture.md": "# Architecture\n\nGateway sits between AI clients and MCP servers.",
    "/src/main.py": 'print("Hello, World!")',
    "/data/config.json": '{"key": "value", "count": 42}',
}


@mcp.tool(
    title="List files in a directory",
    annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False),
)
def list_files(directory: str) -> str:
    """List all files in the given directory path."""
    matches = [p for p in MOCK_FS if p.startswith(directory.rstrip("/") + "/")]
    return json.dumps({"directory": directory, "files": matches, "count": len(matches)})


@mcp.tool(
    title="Read file contents",
    annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False),
)
def read_file(path: str) -> str:
    """Read the contents of a file at the given path."""
    if path not in MOCK_FS:
        raise ToolError(f"File not found: {path}")
    return json.dumps({"path": path, "content": MOCK_FS[path], "size": len(MOCK_FS[path])})


@mcp.tool(
    title="Write file contents",
    annotations=ToolAnnotations(
        read_only_hint=False, destructive_hint=False, idempotent_hint=True
    ),
)
def write_file(path: str, content: str) -> str:
    """Write content to a file at the given path. Creates the file if it doesn't exist."""
    MOCK_FS[path] = content
    return json.dumps({"path": path, "status": "written", "size": len(content)})


@mcp.tool(
    title="Delete a file",
    annotations=ToolAnnotations(
        read_only_hint=False, destructive_hint=True, idempotent_hint=False
    ),
)
def delete_file(path: str) -> str:
    """Delete a file at the given path. This is a destructive operation."""
    if path not in MOCK_FS:
        raise ToolError(f"File not found: {path}")
    del MOCK_FS[path]
    return json.dumps({"path": path, "status": "deleted"})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Mock File Manager MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "streamable-http"],
        default="stdio",
    )
    parser.add_argument("--port", type=int, default=9001)
    args = parser.parse_args()

    if args.transport == "streamable-http":
        mcp.run(transport="streamable-http", host="0.0.0.0", port=args.port)
    else:
        mcp.run()
