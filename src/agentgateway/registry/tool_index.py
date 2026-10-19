"""Aggregated tool registry — indexes tools from all downstream MCP servers."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mcp.types import Tool

logger = logging.getLogger(__name__)


@dataclass
class ToolEntry:
    """A tool plus metadata about where it lives."""

    tool: Tool
    server_name: str


class ToolIndex:
    """Holds the aggregated catalog of tools discovered from all downstream servers."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolEntry] = {}
        self._server_tools: dict[str, list[str]] = field(default_factory=dict) if False else {}

    def register(self, tool: Tool, server_name: str) -> None:
        """Register a tool from a downstream server."""
        if tool.name in self._tools:
            existing = self._tools[tool.name].server_name
            logger.warning(
                "Tool name collision: '%s' from '%s' overwrites '%s'",
                tool.name,
                server_name,
                existing,
            )
        self._tools[tool.name] = ToolEntry(tool=tool, server_name=server_name)
        self._server_tools.setdefault(server_name, []).append(tool.name)

    def clear_server(self, server_name: str) -> None:
        """Remove all tools from a specific server."""
        tool_names = self._server_tools.pop(server_name, [])
        for name in tool_names:
            self._tools.pop(name, None)

    def get_all_tools(self) -> list[Tool]:
        """Return all registered tools."""
        return [entry.tool for entry in self._tools.values()]

    def get_tool_server(self, tool_name: str) -> str | None:
        """Return the server name that owns the given tool."""
        entry = self._tools.get(tool_name)
        return entry.server_name if entry else None

    def get_tool(self, tool_name: str) -> Tool | None:
        """Return the Tool object by name."""
        entry = self._tools.get(tool_name)
        return entry.tool if entry else None

    def get_tools_by_server(self, server_name: str) -> list[Tool]:
        """Return all tools from a specific server."""
        tool_names = self._server_tools.get(server_name, [])
        return [self._tools[n].tool for n in tool_names if n in self._tools]

    @property
    def tool_count(self) -> int:
        return len(self._tools)

    @property
    def server_count(self) -> int:
        return len(self._server_tools)
