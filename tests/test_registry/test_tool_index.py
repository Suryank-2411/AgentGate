"""Tests for the ToolIndex."""

from mcp.types import Tool

from agentgateway.registry.tool_index import ToolIndex


class TestToolIndex:
    def _make_tool(self, name: str, desc: str = "A tool") -> Tool:
        return Tool(name=name, description=desc, inputSchema={"type": "object", "properties": {}})

    def test_register_and_get(self):
        idx = ToolIndex()
        tool = self._make_tool("list_files")
        idx.register(tool, "file-manager")
        assert idx.tool_count == 1
        assert idx.get_tool_server("list_files") == "file-manager"
        assert idx.get_tool("list_files") is tool

    def test_get_all_tools(self):
        idx = ToolIndex()
        idx.register(self._make_tool("a"), "s1")
        idx.register(self._make_tool("b"), "s1")
        idx.register(self._make_tool("c"), "s2")
        all_tools = idx.get_all_tools()
        assert len(all_tools) == 3
        assert {t.name for t in all_tools} == {"a", "b", "c"}

    def test_get_tools_by_server(self):
        idx = ToolIndex()
        idx.register(self._make_tool("a"), "s1")
        idx.register(self._make_tool("b"), "s2")
        assert len(idx.get_tools_by_server("s1")) == 1
        assert idx.get_tools_by_server("s1")[0].name == "a"

    def test_clear_server(self):
        idx = ToolIndex()
        idx.register(self._make_tool("a"), "s1")
        idx.register(self._make_tool("b"), "s1")
        idx.register(self._make_tool("c"), "s2")
        idx.clear_server("s1")
        assert idx.tool_count == 1
        assert idx.get_tool_server("a") is None
        assert idx.get_tool_server("c") == "s2"

    def test_collision_warning(self):
        idx = ToolIndex()
        idx.register(self._make_tool("x"), "s1")
        idx.register(self._make_tool("x"), "s2")
        # Last one wins
        assert idx.get_tool_server("x") == "s2"
        assert idx.tool_count == 1

    def test_missing_tool(self):
        idx = ToolIndex()
        assert idx.get_tool("nonexistent") is None
        assert idx.get_tool_server("nonexistent") is None
