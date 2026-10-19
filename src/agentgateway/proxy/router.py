"""Request routing utilities for the gateway proxy."""

from __future__ import annotations

from agentgateway.registry.tool_index import ToolIndex


def resolve_tool_route(tool_name: str, tool_index: ToolIndex) -> str | None:
    """Resolve which downstream server should handle a tool call."""
    return tool_index.get_tool_server(tool_name)
