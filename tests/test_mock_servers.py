"""Tests for mock MCP servers using in-memory Client."""

import json

import pytest

from mcp import Client


class TestFileManagerServer:
    async def _make_client(self):
        from mock_servers.file_manager import mcp
        return Client(mcp, raise_exceptions=True)

    async def test_list_tools(self):
        async with await self._make_client() as client:
            result = await client.list_tools()
            names = [t.name for t in result.tools]
            assert "list_files" in names
            assert "read_file" in names
            assert "write_file" in names
            assert "delete_file" in names
            assert len(result.tools) == 4

    async def test_list_files(self):
        async with await self._make_client() as client:
            result = await client.call_tool("list_files", {"directory": "/docs"})
            data = json.loads(result.content[0].text)
            assert data["count"] == 2
            assert "/docs/readme.txt" in data["files"]

    async def test_list_files_empty_dir(self):
        async with await self._make_client() as client:
            result = await client.call_tool("list_files", {"directory": "/nonexistent"})
            data = json.loads(result.content[0].text)
            assert data["count"] == 0

    async def test_read_file(self):
        async with await self._make_client() as client:
            result = await client.call_tool("read_file", {"path": "/docs/readme.txt"})
            data = json.loads(result.content[0].text)
            assert "AgentGateWay" in data["content"]

    async def test_read_file_not_found(self):
        async with await self._make_client() as client:
            result = await client.call_tool("read_file", {"path": "/missing.txt"})
            assert result.is_error is True
            assert "not found" in result.content[0].text.lower()

    async def test_write_file(self):
        async with await self._make_client() as client:
            result = await client.call_tool(
                "write_file", {"path": "/tmp/test.txt", "content": "hello"}
            )
            data = json.loads(result.content[0].text)
            assert data["status"] == "written"

    async def test_delete_file(self):
        async with await self._make_client() as client:
            await client.call_tool("write_file", {"path": "/tmp/del.txt", "content": "x"})
            result = await client.call_tool("delete_file", {"path": "/tmp/del.txt"})
            data = json.loads(result.content[0].text)
            assert data["status"] == "deleted"


class TestDatabaseQueryServer:
    async def _make_client(self):
        from mock_servers.database_query import mcp
        return Client(mcp, raise_exceptions=True)

    async def test_list_tools(self):
        async with await self._make_client() as client:
            result = await client.list_tools()
            names = [t.name for t in result.tools]
            assert "execute_query" in names
            assert "list_tables" in names
            assert "describe_table" in names
            assert len(result.tools) == 3

    async def test_execute_select_query(self):
        async with await self._make_client() as client:
            result = await client.call_tool(
                "execute_query", {"sql": "SELECT * FROM users", "database": "app_db"}
            )
            data = json.loads(result.content[0].text)
            assert data["row_count"] == 3
            assert data["rows"][0]["username"] == "alice"

    async def test_execute_query_no_match(self):
        async with await self._make_client() as client:
            result = await client.call_tool(
                "execute_query", {"sql": "SELECT * FROM nonexistent", "database": "app_db"}
            )
            data = json.loads(result.content[0].text)
            assert data["row_count"] == 0

    async def test_list_tables(self):
        async with await self._make_client() as client:
            result = await client.call_tool("list_tables", {"database": "app_db"})
            data = json.loads(result.content[0].text)
            assert "users" in data["tables"]
            assert "orders" in data["tables"]

    async def test_describe_table(self):
        async with await self._make_client() as client:
            result = await client.call_tool(
                "describe_table", {"table": "users", "database": "app_db"}
            )
            data = json.loads(result.content[0].text)
            col_names = [c["name"] for c in data["columns"]]
            assert "id" in col_names
            assert "username" in col_names

    async def test_describe_missing_table(self):
        async with await self._make_client() as client:
            result = await client.call_tool(
                "describe_table", {"table": "missing", "database": "app_db"}
            )
            assert result.is_error is True

    async def test_missing_database(self):
        async with await self._make_client() as client:
            result = await client.call_tool(
                "list_tables", {"database": "nonexistent_db"}
            )
            assert result.is_error is True
