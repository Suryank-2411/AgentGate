"""OPA HTTP sidecar policy engine — evaluates Rego policies via the OPA REST API."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import httpx

from agentgateway.policy.engine import PolicyDecision, PolicyEngine

if TYPE_CHECKING:
    from mcp.types import Tool

    from agentgateway.auth.jwt_validator import TokenClaims
    from agentgateway.registry.tool_index import ToolIndex

logger = logging.getLogger(__name__)


class OPAPolicyEngine(PolicyEngine):
    """
    Policy engine that delegates authorization decisions to an OPA sidecar
    over its REST API.

    Expects OPA running at the configured URL with policies loaded under
    the `agentgateway` package.
    """

    def __init__(self, opa_url: str, tool_index: ToolIndex | None = None) -> None:
        self._opa_url = opa_url.rstrip("/")
        self._tool_index = tool_index
        self._http = httpx.AsyncClient(timeout=5.0)

    async def check_tool_access(
        self, user: TokenClaims, tool_name: str, server_name: str
    ) -> PolicyDecision:
        """Query OPA for tool access authorization."""
        input_data = {
            "user": {
                "id": user.user_id,
                "roles": user.roles,
                "email": user.email,
            },
            "tool_name": tool_name,
            "server_name": server_name,
        }
        return await self._query_policy("agentgateway/tool_access", input_data)

    async def check_payload(
        self, user: TokenClaims, tool_name: str, arguments: dict
    ) -> PolicyDecision:
        """Query OPA for payload-level policy checks."""
        input_data = {
            "user": {
                "id": user.user_id,
                "roles": user.roles,
            },
            "tool_name": tool_name,
            "arguments": arguments,
        }
        return await self._query_policy("agentgateway/payload_guard", input_data)

    async def filter_tools(self, user: TokenClaims, tools: list[Tool]) -> list[Tool]:
        """Filter tools by evaluating each against OPA policy."""
        filtered = []
        for tool in tools:
            server_name = ""
            if self._tool_index:
                server_name = self._tool_index.get_tool_server(tool.name) or ""
            decision = await self.check_tool_access(user, tool.name, server_name)
            if decision.allowed:
                filtered.append(tool)
        return filtered

    async def _query_policy(self, policy_path: str, input_data: dict[str, Any]) -> PolicyDecision:
        """Send a query to OPA and parse the result."""
        url = f"{self._opa_url}/v1/data/{policy_path}"
        try:
            response = await self._http.post(url, json={"input": input_data})
            response.raise_for_status()
            data = response.json()

            result = data.get("result", {})

            # Check for explicit deny
            if result.get("deny"):
                deny_reasons = result["deny"] if isinstance(result["deny"], list) else [str(result["deny"])]
                return PolicyDecision(
                    allowed=False,
                    reason="; ".join(str(r) for r in deny_reasons),
                )

            # Check for allow
            allowed = result.get("allow", False)
            return PolicyDecision(allowed=allowed)

        except httpx.ConnectError:
            logger.error("OPA unreachable at %s — defaulting to deny", self._opa_url)
            return PolicyDecision(allowed=False, reason="OPA service unreachable")
        except Exception as exc:
            logger.error("OPA query failed: %s", exc)
            return PolicyDecision(allowed=False, reason=f"OPA error: {exc}")

    async def close(self) -> None:
        await self._http.aclose()
