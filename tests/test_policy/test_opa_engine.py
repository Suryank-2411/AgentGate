"""Tests for OPA HTTP policy engine — uses mocked HTTP responses."""

import json

import httpx
import pytest

from agentgateway.auth.jwt_validator import TokenClaims
from agentgateway.policy.opa_engine import OPAPolicyEngine


class MockOPATransport(httpx.AsyncBaseTransport):
    """Mock transport simulating OPA REST API responses."""

    def __init__(self):
        self._responses: dict[str, dict] = {}

    def set_response(self, path: str, result: dict):
        self._responses[path] = result

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path in self._responses:
            return httpx.Response(
                200,
                json={"result": self._responses[path]},
                request=request,
            )
        return httpx.Response(404, json={"error": "not found"}, request=request)


@pytest.fixture
def mock_transport():
    return MockOPATransport()


@pytest.fixture
def opa_engine(mock_transport: MockOPATransport) -> OPAPolicyEngine:
    engine = OPAPolicyEngine(opa_url="http://opa-test:8181")
    engine._http = httpx.AsyncClient(transport=mock_transport)
    return engine


class TestOPAEngine:
    async def test_allow_admin(self, opa_engine, mock_transport):
        mock_transport.set_response(
            "/v1/data/agentgateway/tool_access",
            {"allow": True},
        )
        admin = TokenClaims(user_id="admin", roles=["admin"])
        decision = await opa_engine.check_tool_access(admin, "delete_file", "file-manager")
        assert decision.allowed is True

    async def test_deny_non_admin_delete(self, opa_engine, mock_transport):
        mock_transport.set_response(
            "/v1/data/agentgateway/tool_access",
            {"allow": False, "deny": True},
        )
        dev = TokenClaims(user_id="dev", roles=["developer"])
        decision = await opa_engine.check_tool_access(dev, "delete_file", "file-manager")
        assert decision.allowed is False

    async def test_payload_allow(self, opa_engine, mock_transport):
        mock_transport.set_response(
            "/v1/data/agentgateway/payload_guard",
            {"allow": True},
        )
        user = TokenClaims(user_id="u", roles=["developer"])
        decision = await opa_engine.check_payload(
            user, "execute_query", {"sql": "SELECT * FROM users"}
        )
        assert decision.allowed is True

    async def test_payload_deny_drop(self, opa_engine, mock_transport):
        mock_transport.set_response(
            "/v1/data/agentgateway/payload_guard",
            {"allow": True, "deny": ["SQL DROP detected"]},
        )
        user = TokenClaims(user_id="u", roles=["developer"])
        decision = await opa_engine.check_payload(
            user, "execute_query", {"sql": "DROP TABLE users"}
        )
        assert decision.allowed is False
        assert "DROP" in decision.reason

    async def test_opa_unreachable_defaults_to_deny(self):
        engine = OPAPolicyEngine(opa_url="http://unreachable:9999")
        engine._http = httpx.AsyncClient(timeout=0.1)
        user = TokenClaims(user_id="u", roles=["admin"])
        decision = await engine.check_tool_access(user, "list_files", "file-manager")
        assert decision.allowed is False
        assert decision.reason is not None
