"""Tests for the ServerManager with in-memory MCP servers."""

import json

import pytest

from mcp import Client

from agentgateway.config.loader import ServerConfig
from agentgateway.registry.server_manager import ServerManager
from agentgateway.registry.tool_index import ToolIndex


class TestServerManagerInMemory:
    """Test ServerManager using in-memory mock server connections."""

    async def test_tool_discovery_via_direct_client(self):
        """Verify we can discover tools from mock servers using direct Client."""
        from mock_servers.database_query import mcp as db_mcp
        from mock_servers.file_manager import mcp as fm_mcp

        tool_index = ToolIndex()

        async with Client(fm_mcp, raise_exceptions=True) as fm_client:
            result = await fm_client.list_tools()
            for tool in result.tools:
                tool_index.register(tool, "file-manager")

        async with Client(db_mcp, raise_exceptions=True) as db_client:
            result = await db_client.list_tools()
            for tool in result.tools:
                tool_index.register(tool, "database-query")

        assert tool_index.tool_count == 7
        assert tool_index.server_count == 2
        assert tool_index.get_tool_server("list_files") == "file-manager"
        assert tool_index.get_tool_server("execute_query") == "database-query"

    async def test_proxy_call_through_client(self):
        """Verify we can proxy a tool call through the Client."""
        from mock_servers.file_manager import mcp as fm_mcp

        async with Client(fm_mcp, raise_exceptions=True) as client:
            result = await client.call_tool("list_files", {"directory": "/docs"})
            data = json.loads(result.content[0].text)
            assert data["count"] == 2

    async def test_invalid_transport_raises(self):
        config = ServerConfig(name="bad", transport="grpc")
        mgr = ServerManager([config], ToolIndex())
        # start should log error but not crash
        await mgr.start()
        assert "bad" not in mgr.connected_servers
        await mgr.stop()

    async def test_get_client_missing_raises(self):
        mgr = ServerManager([], ToolIndex())
        with pytest.raises(KeyError, match="No active connection"):
            mgr.get_client("nonexistent")
