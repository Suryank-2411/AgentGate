"""Tests for the gateway proxy server with in-memory downstream connections."""

import json

import pytest

from mcp import Client
from mcp.types import TextContent

from agentgateway.config.loader import ServerConfig
from agentgateway.proxy.gateway_server import GatewayServer
from agentgateway.registry.server_manager import ServerManager
from agentgateway.registry.tool_index import ToolIndex


async def _build_gateway_with_mock_tools():
    """Build a GatewayServer backed by in-memory mock servers."""
    from mock_servers.database_query import mcp as db_mcp
    from mock_servers.file_manager import mcp as fm_mcp

    tool_index = ToolIndex()

    # Discover tools from mock servers via direct in-memory clients
    async with Client(fm_mcp, raise_exceptions=True) as fm_client:
        result = await fm_client.list_tools()
        for tool in result.tools:
            tool_index.register(tool, "file-manager")

    async with Client(db_mcp, raise_exceptions=True) as db_client:
        result = await db_client.list_tools()
        for tool in result.tools:
            tool_index.register(tool, "database-query")

    # Build a ServerManager with no configs (we'll mock get_client)
    server_manager = ServerManager([], tool_index)

    return GatewayServer(tool_index, server_manager), fm_mcp, db_mcp


class TestGatewayServer:
    async def test_list_tools_returns_all_downstream_tools(self):
        gateway, fm_mcp, db_mcp = await _build_gateway_with_mock_tools()

        # Connect to the gateway's low-level server in-memory
        async with Client(gateway.server, raise_exceptions=True) as client:
            result = await client.list_tools()
            names = [t.name for t in result.tools]
            assert len(names) == 7
            assert "list_files" in names
            assert "read_file" in names
            assert "write_file" in names
            assert "delete_file" in names
            assert "execute_query" in names
            assert "list_tables" in names
            assert "describe_table" in names

    async def test_proxy_tool_call_file_manager(self):
        gateway, fm_mcp, db_mcp = await _build_gateway_with_mock_tools()

        # Patch the server_manager to return in-memory clients
        class MockServerManager:
            def get_client(self, name):
                raise KeyError(f"No real connection in test for {name}")

        # We need a live client for the proxy. Use a different approach:
        # connect a client to the downstream AND the gateway simultaneously
        async with Client(fm_mcp, raise_exceptions=True) as fm_client:
            # Monkey-patch get_client to return the live fm_client
            original_get = gateway._server_manager.get_client

            def patched_get(name):
                if name == "file-manager":
                    return fm_client
                raise KeyError(f"No connection to {name}")

            gateway._server_manager.get_client = patched_get

            async with Client(gateway.server, raise_exceptions=True) as gw_client:
                result = await gw_client.call_tool("list_files", {"directory": "/docs"})
                assert not result.is_error
                data = json.loads(result.content[0].text)
                assert data["count"] == 2

    async def test_proxy_tool_call_database(self):
        gateway, fm_mcp, db_mcp = await _build_gateway_with_mock_tools()

        async with Client(db_mcp, raise_exceptions=True) as db_client:
            gateway._server_manager.get_client = lambda name: (
                db_client if name == "database-query" else (_ for _ in ()).throw(KeyError(name))
            )

            async with Client(gateway.server, raise_exceptions=True) as gw_client:
                result = await gw_client.call_tool(
                    "execute_query", {"sql": "SELECT * FROM users", "database": "app_db"}
                )
                assert not result.is_error
                data = json.loads(result.content[0].text)
                assert data["row_count"] == 3

    async def test_unknown_tool_returns_error(self):
        gateway, fm_mcp, db_mcp = await _build_gateway_with_mock_tools()

        async with Client(gateway.server, raise_exceptions=True) as gw_client:
            result = await gw_client.call_tool("nonexistent_tool", {})
            # The low-level server will propagate the ValueError as an error
            assert result.is_error

    async def test_disconnected_server_returns_error(self):
        gateway, fm_mcp, db_mcp = await _build_gateway_with_mock_tools()

        # Don't patch get_client — it will raise KeyError
        async with Client(gateway.server, raise_exceptions=True) as gw_client:
            result = await gw_client.call_tool("list_files", {"directory": "/"})
            assert result.is_error
