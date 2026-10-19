"""End-to-end integration tests for the full gateway pipeline.

These tests wire together all gateway subsystems using in-memory
mock servers — no network, no Docker, no external dependencies.
"""

import json
from pathlib import Path

import pytest

from mcp import Client
from mcp.types import Tool

from agentgateway.auth.jwt_validator import JWTValidator, TokenClaims
from agentgateway.config.loader import RolesConfig, RoleConfig, load_roles_config
from agentgateway.config.settings import AuthSettings, GuardrailsSettings
from agentgateway.db.database import Database
from agentgateway.guardrails.sanitizer import Sanitizer
from agentgateway.policy.local_engine import LocalPolicyEngine
from agentgateway.proxy.gateway_server import GatewayServer
from agentgateway.proxy.rest_virtualizer import RESTVirtualizer
from agentgateway.registry.server_manager import ServerManager
from agentgateway.registry.tool_index import ToolIndex
from agentgateway.telemetry.audit_log import AuditLogger, AuditFilter
from tests.conftest import TEST_JWT_SECRET, create_test_jwt


# ── Fixtures ──


@pytest.fixture
async def integration_db(tmp_path):
    db = Database(str(tmp_path / "integration.db"))
    await db.connect()
    yield db
    await db.disconnect()


@pytest.fixture
def roles_config():
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
async def full_gateway(integration_db, roles_config):
    """Build a fully-wired gateway with mock downstream servers."""
    from mock_servers.database_query import mcp as db_mcp
    from mock_servers.file_manager import mcp as fm_mcp

    tool_index = ToolIndex()

    # Discover tools from mock servers
    async with Client(fm_mcp, raise_exceptions=True) as fm_client:
        result = await fm_client.list_tools()
        for tool in result.tools:
            tool_index.register(tool, "file-manager")

    async with Client(db_mcp, raise_exceptions=True) as db_client:
        result = await db_client.list_tools()
        for tool in result.tools:
            tool_index.register(tool, "database-query")

    server_manager = ServerManager([], tool_index)

    # Build subsystems
    policy_engine = LocalPolicyEngine(roles_config, tool_index)
    sanitizer = Sanitizer(GuardrailsSettings(enabled=True))
    audit_logger = AuditLogger(integration_db)

    # Build gateway
    gateway = GatewayServer(tool_index, server_manager)
    gateway.policy_engine = policy_engine
    gateway.sanitizer = sanitizer
    gateway.audit_logger = audit_logger

    return gateway, fm_mcp, db_mcp, audit_logger


def _patch_clients(gateway, fm_client, db_client):
    """Patch server_manager.get_client to return in-memory clients."""
    def get_client(name):
        if name == "file-manager":
            return fm_client
        if name == "database-query":
            return db_client
        raise KeyError(f"No connection to {name}")
    gateway._server_manager.get_client = get_client


# ── Integration Tests ──


class TestFullPipeline:
    """Tests exercising the complete Auth → Policy → Guardrails → Proxy → Audit pipeline."""

    async def test_admin_sees_all_tools_and_can_call_any(self, full_gateway):
        gateway, fm_mcp, db_mcp, audit_logger = full_gateway
        admin = TokenClaims(user_id="admin", roles=["admin"])
        gateway.auth_extractor = lambda ctx: admin

        async with Client(fm_mcp, raise_exceptions=True) as fm_client, \
                   Client(db_mcp, raise_exceptions=True) as db_client:
            _patch_clients(gateway, fm_client, db_client)

            async with Client(gateway.server, raise_exceptions=True) as gw_client:
                # Admin sees all 7 tools
                tools = await gw_client.list_tools()
                assert len(tools.tools) == 7

                # Admin can call delete_file
                await gw_client.call_tool("write_file", {"path": "/tmp/x", "content": "y"})
                result = await gw_client.call_tool("delete_file", {"path": "/tmp/x"})
                assert not result.is_error

    async def test_developer_denied_delete_file(self, full_gateway):
        gateway, fm_mcp, db_mcp, audit_logger = full_gateway
        dev = TokenClaims(user_id="dev-user", roles=["developer"])
        gateway.auth_extractor = lambda ctx: dev

        async with Client(fm_mcp, raise_exceptions=True) as fm_client, \
                   Client(db_mcp, raise_exceptions=True) as db_client:
            _patch_clients(gateway, fm_client, db_client)

            async with Client(gateway.server, raise_exceptions=True) as gw_client:
                # Developer sees 6 tools (no delete_file)
                tools = await gw_client.list_tools()
                names = {t.name for t in tools.tools}
                assert "delete_file" not in names
                assert len(names) == 6

                # Developer trying delete_file is denied
                result = await gw_client.call_tool("delete_file", {"path": "/docs/readme.txt"})
                assert result.is_error
                assert "denied" in result.content[0].text.lower()

    async def test_analyst_restricted_to_db_tools(self, full_gateway):
        gateway, fm_mcp, db_mcp, audit_logger = full_gateway
        analyst = TokenClaims(user_id="analyst", roles=["analyst"])
        gateway.auth_extractor = lambda ctx: analyst

        async with Client(fm_mcp, raise_exceptions=True) as fm_client, \
                   Client(db_mcp, raise_exceptions=True) as db_client:
            _patch_clients(gateway, fm_client, db_client)

            async with Client(gateway.server, raise_exceptions=True) as gw_client:
                tools = await gw_client.list_tools()
                names = {t.name for t in tools.tools}
                assert names == {"execute_query", "list_tables", "describe_table"}

                # Can call allowed tool
                result = await gw_client.call_tool(
                    "execute_query", {"sql": "SELECT * FROM users", "database": "app_db"}
                )
                assert not result.is_error

                # Cannot call file tools
                result = await gw_client.call_tool("list_files", {"directory": "/"})
                assert result.is_error

    async def test_sql_injection_blocked_by_guardrails(self, full_gateway):
        gateway, fm_mcp, db_mcp, audit_logger = full_gateway
        admin = TokenClaims(user_id="admin", roles=["admin"])
        gateway.auth_extractor = lambda ctx: admin

        async with Client(fm_mcp, raise_exceptions=True) as fm_client, \
                   Client(db_mcp, raise_exceptions=True) as db_client:
            _patch_clients(gateway, fm_client, db_client)

            async with Client(gateway.server, raise_exceptions=True) as gw_client:
                result = await gw_client.call_tool(
                    "execute_query", {"sql": "DROP TABLE users", "database": "app_db"}
                )
                assert result.is_error
                assert "guardrail" in result.content[0].text.lower() or "blocked" in result.content[0].text.lower()

    async def test_path_traversal_blocked(self, full_gateway):
        gateway, fm_mcp, db_mcp, audit_logger = full_gateway
        admin = TokenClaims(user_id="admin", roles=["admin"])
        gateway.auth_extractor = lambda ctx: admin

        async with Client(fm_mcp, raise_exceptions=True) as fm_client, \
                   Client(db_mcp, raise_exceptions=True) as db_client:
            _patch_clients(gateway, fm_client, db_client)

            async with Client(gateway.server, raise_exceptions=True) as gw_client:
                result = await gw_client.call_tool(
                    "read_file", {"path": "../../etc/passwd"}
                )
                assert result.is_error

    async def test_audit_log_populated(self, full_gateway):
        gateway, fm_mcp, db_mcp, audit_logger = full_gateway
        dev = TokenClaims(user_id="audit-test-user", roles=["developer"])
        gateway.auth_extractor = lambda ctx: dev

        async with Client(fm_mcp, raise_exceptions=True) as fm_client, \
                   Client(db_mcp, raise_exceptions=True) as db_client:
            _patch_clients(gateway, fm_client, db_client)

            async with Client(gateway.server, raise_exceptions=True) as gw_client:
                # Successful call
                await gw_client.call_tool("list_files", {"directory": "/docs"})
                # Denied call
                await gw_client.call_tool("delete_file", {"path": "/x"})

                # Check audit trail
                logs = await audit_logger.query_logs(AuditFilter(user_id="audit-test-user"))
                assert len(logs) >= 1

                success_logs = await audit_logger.query_logs(
                    AuditFilter(user_id="audit-test-user", status="success")
                )
                assert len(success_logs) >= 1
                assert success_logs[0]["tool_name"] == "list_files"

    async def test_successful_proxy_returns_correct_data(self, full_gateway):
        gateway, fm_mcp, db_mcp, audit_logger = full_gateway
        dev = TokenClaims(user_id="dev", roles=["developer"])
        gateway.auth_extractor = lambda ctx: dev

        async with Client(fm_mcp, raise_exceptions=True) as fm_client, \
                   Client(db_mcp, raise_exceptions=True) as db_client:
            _patch_clients(gateway, fm_client, db_client)

            async with Client(gateway.server, raise_exceptions=True) as gw_client:
                result = await gw_client.call_tool(
                    "execute_query", {"sql": "SELECT * FROM users", "database": "app_db"}
                )
                assert not result.is_error
                data = json.loads(result.content[0].text)
                assert data["row_count"] == 3
                assert data["rows"][0]["username"] == "alice"


class TestRESTVirtualization:
    def test_openapi_spec_generates_tools(self):
        spec_path = str(Path(__file__).parent.parent.parent / "config" / "sample_api.yaml")
        v = RESTVirtualizer()
        tools = v.load_spec(spec_path, base_url="http://localhost:9003", server_name="pet-store")
        names = [t.name for t in tools]
        assert "list_pets" in names
        assert "create_pet" in names
        assert "get_pet" in names
        assert "delete_pet" in names

    def test_virtualized_tools_can_register_in_index(self):
        spec_path = str(Path(__file__).parent.parent.parent / "config" / "sample_api.yaml")
        v = RESTVirtualizer()
        tools = v.load_spec(spec_path, base_url="http://localhost:9003", server_name="pet-store")

        idx = ToolIndex()
        for tool in tools:
            idx.register(tool, "pet-store")

        assert idx.tool_count == 4
        assert idx.get_tool_server("create_pet") == "pet-store"
