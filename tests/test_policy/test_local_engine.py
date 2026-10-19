"""Tests for the local YAML-based RBAC policy engine."""

import pytest

from mcp.types import Tool

from agentgateway.auth.jwt_validator import TokenClaims
from agentgateway.config.loader import RoleConfig, RolesConfig
from agentgateway.policy.local_engine import LocalPolicyEngine
from agentgateway.registry.tool_index import ToolIndex


def _make_tool(name: str) -> Tool:
    return Tool(name=name, description=f"Tool {name}", inputSchema={"type": "object", "properties": {}})


@pytest.fixture
def tool_index() -> ToolIndex:
    idx = ToolIndex()
    for name in ["list_files", "read_file", "write_file", "delete_file"]:
        idx.register(_make_tool(name), "file-manager")
    for name in ["execute_query", "list_tables", "describe_table"]:
        idx.register(_make_tool(name), "database-query")
    return idx


@pytest.fixture
def roles_config() -> RolesConfig:
    return RolesConfig(
        roles={
            "admin": RoleConfig(allowed_tools=["*"], denied_tools=[], allowed_servers=["*"]),
            "developer": RoleConfig(
                allowed_tools=["list_files", "read_file", "write_file", "execute_query", "list_tables", "describe_table"],
                denied_tools=["delete_file"],
                allowed_servers=["*"],
            ),
            "analyst": RoleConfig(
                allowed_tools=["execute_query", "list_tables", "describe_table"],
                denied_tools=[],
                allowed_servers=["database-query"],
            ),
        }
    )


@pytest.fixture
def engine(roles_config, tool_index) -> LocalPolicyEngine:
    return LocalPolicyEngine(roles_config, tool_index)


class TestLocalPolicyEngine:
    async def test_admin_sees_all_tools(self, engine, tool_index):
        admin = TokenClaims(user_id="admin", roles=["admin"])
        tools = tool_index.get_all_tools()
        filtered = await engine.filter_tools(admin, tools)
        assert len(filtered) == 7

    async def test_developer_sees_subset(self, engine, tool_index):
        dev = TokenClaims(user_id="dev", roles=["developer"])
        tools = tool_index.get_all_tools()
        filtered = await engine.filter_tools(dev, tools)
        names = {t.name for t in filtered}
        assert "delete_file" not in names
        assert "list_files" in names
        assert "execute_query" in names
        assert len(filtered) == 6

    async def test_analyst_sees_only_db_tools(self, engine, tool_index):
        analyst = TokenClaims(user_id="analyst", roles=["analyst"])
        tools = tool_index.get_all_tools()
        filtered = await engine.filter_tools(analyst, tools)
        names = {t.name for t in filtered}
        assert names == {"execute_query", "list_tables", "describe_table"}

    async def test_admin_can_call_any_tool(self, engine):
        admin = TokenClaims(user_id="admin", roles=["admin"])
        decision = await engine.check_tool_access(admin, "delete_file", "file-manager")
        assert decision.allowed is True

    async def test_developer_denied_delete_file(self, engine):
        dev = TokenClaims(user_id="dev", roles=["developer"])
        decision = await engine.check_tool_access(dev, "delete_file", "file-manager")
        assert decision.allowed is False
        assert "denied" in decision.reason.lower()

    async def test_analyst_denied_file_tools(self, engine):
        analyst = TokenClaims(user_id="analyst", roles=["analyst"])
        decision = await engine.check_tool_access(analyst, "list_files", "file-manager")
        assert decision.allowed is False

    async def test_analyst_allowed_db_tool(self, engine):
        analyst = TokenClaims(user_id="analyst", roles=["analyst"])
        decision = await engine.check_tool_access(analyst, "execute_query", "database-query")
        assert decision.allowed is True

    async def test_no_roles_denied(self, engine, tool_index):
        nobody = TokenClaims(user_id="nobody", roles=[])
        decision = await engine.check_tool_access(nobody, "list_files", "file-manager")
        assert decision.allowed is False

        filtered = await engine.filter_tools(nobody, tool_index.get_all_tools())
        assert len(filtered) == 0

    async def test_unknown_role_ignored(self, engine):
        user = TokenClaims(user_id="u", roles=["unknown_role"])
        decision = await engine.check_tool_access(user, "list_files", "file-manager")
        assert decision.allowed is False
