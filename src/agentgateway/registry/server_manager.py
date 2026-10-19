"""Downstream MCP server connection manager."""

from __future__ import annotations

import logging
from contextlib import AsyncExitStack
from typing import Any

from mcp import Client, StdioServerParameters

from agentgateway.config.loader import ServerConfig
from agentgateway.registry.tool_index import ToolIndex

logger = logging.getLogger(__name__)


class ServerConnection:
    """Wraps a downstream MCP server connection."""

    def __init__(self, config: ServerConfig) -> None:
        self.config = config
        self.client: Client | None = None
        self.healthy: bool = False

    @property
    def name(self) -> str:
        return self.config.name


class ServerManager:
    """Manages lifecycle and connections to all downstream MCP servers."""

    def __init__(self, server_configs: list[ServerConfig], tool_index: ToolIndex) -> None:
        self._configs = server_configs
        self._tool_index = tool_index
        self._connections: dict[str, ServerConnection] = {}
        self._exit_stack = AsyncExitStack()

    async def start(self) -> None:
        """Connect to all configured downstream servers and discover their tools."""
        await self._exit_stack.__aenter__()

        for config in self._configs:
            if config.transport == "rest":
                # REST virtualization is handled separately
                logger.info("Skipping REST server '%s' — handled by virtualizer", config.name)
                continue
            try:
                await self._connect_server(config)
            except Exception:
                logger.exception("Failed to connect to server '%s'", config.name)

    async def _connect_server(self, config: ServerConfig) -> None:
        """Connect to a single downstream server."""
        conn = ServerConnection(config)

        if config.transport == "stdio":
            if not config.command:
                raise ValueError(f"Server '{config.name}': stdio transport requires 'command'")
            params = StdioServerParameters(
                command=config.command,
                args=config.args,
                env=config.env if config.env else None,
            )
            client = Client(params)
        elif config.transport == "streamable-http":
            if not config.url:
                raise ValueError(
                    f"Server '{config.name}': streamable-http transport requires 'url'"
                )
            client = Client(config.url)
        else:
            raise ValueError(f"Server '{config.name}': unsupported transport '{config.transport}'")

        # Enter the client's async context via our exit stack
        connected_client = await self._exit_stack.enter_async_context(client)
        conn.client = connected_client
        conn.healthy = True
        self._connections[config.name] = conn

        # Discover tools
        await self._discover_tools(conn)
        logger.info(
            "Connected to '%s' (%s): %d tools discovered",
            config.name,
            config.transport,
            len(self._tool_index.get_tools_by_server(config.name)),
        )

    async def _discover_tools(self, conn: ServerConnection) -> None:
        """Discover tools from a connected server."""
        if not conn.client:
            return
        self._tool_index.clear_server(conn.name)
        result = await conn.client.list_tools()
        for tool in result.tools:
            self._tool_index.register(tool, conn.name)

    async def stop(self) -> None:
        """Disconnect from all servers."""
        await self._exit_stack.aclose()
        self._connections.clear()
        logger.info("All downstream connections closed")

    def get_client(self, server_name: str) -> Client:
        """Get the connected Client for a downstream server."""
        conn = self._connections.get(server_name)
        if not conn or not conn.client:
            raise KeyError(f"No active connection to server '{server_name}'")
        return conn.client

    def is_healthy(self, server_name: str) -> bool:
        conn = self._connections.get(server_name)
        return conn.healthy if conn else False

    @property
    def connected_servers(self) -> list[str]:
        return list(self._connections.keys())
