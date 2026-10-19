"""Local YAML-based RBAC policy engine."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from agentgateway.config.loader import RolesConfig
from agentgateway.policy.engine import PolicyDecision, PolicyEngine
from agentgateway.registry.tool_index import ToolIndex

if TYPE_CHECKING:
    from mcp.types import Tool

    from agentgateway.auth.jwt_validator import TokenClaims

logger = logging.getLogger(__name__)


class LocalPolicyEngine(PolicyEngine):
    """
    RBAC policy engine backed by roles.yaml configuration.

    Evaluates role → allowed_tools / denied_tools / allowed_servers mappings.
    """

    def __init__(self, roles_config: RolesConfig, tool_index: ToolIndex) -> None:
        self._roles = roles_config.roles
        self._tool_index = tool_index

    def _get_user_permissions(self, user: TokenClaims) -> tuple[set[str], set[str], set[str]]:
        """
        Compute the union of allowed_tools, denied_tools, and allowed_servers
        across all of the user's roles.
        """
        allowed_tools: set[str] = set()
        denied_tools: set[str] = set()
        allowed_servers: set[str] = set()

        for role_name in user.roles:
            role = self._roles.get(role_name)
            if not role:
                logger.warning("Unknown role '%s' for user '%s'", role_name, user.user_id)
                continue
            allowed_tools.update(role.allowed_tools)
            denied_tools.update(role.denied_tools)
            allowed_servers.update(role.allowed_servers)

        return allowed_tools, denied_tools, allowed_servers

    def _is_tool_allowed(
        self,
        tool_name: str,
        server_name: str,
        allowed_tools: set[str],
        denied_tools: set[str],
        allowed_servers: set[str],
    ) -> tuple[bool, str | None]:
        """Check if a specific tool is allowed given computed permissions."""
        # Explicit deny always wins
        if tool_name in denied_tools:
            return False, f"Tool '{tool_name}' is explicitly denied"

        # Check server-level access
        if "*" not in allowed_servers and server_name not in allowed_servers:
            return False, f"Server '{server_name}' is not in allowed servers"

        # Check tool-level access
        if "*" in allowed_tools:
            return True, None
        if tool_name in allowed_tools:
            return True, None

        return False, f"Tool '{tool_name}' is not in allowed tools"

    async def check_tool_access(
        self, user: TokenClaims, tool_name: str, server_name: str
    ) -> PolicyDecision:
        allowed_tools, denied_tools, allowed_servers = self._get_user_permissions(user)

        if not allowed_tools and not user.roles:
            return PolicyDecision(allowed=False, reason="No roles assigned")

        allowed, reason = self._is_tool_allowed(
            tool_name, server_name, allowed_tools, denied_tools, allowed_servers
        )
        return PolicyDecision(allowed=allowed, reason=reason)

    async def check_payload(
        self, user: TokenClaims, tool_name: str, arguments: dict
    ) -> PolicyDecision:
        # Local engine delegates payload checks to the guardrails layer
        return PolicyDecision(allowed=True)

    async def filter_tools(self, user: TokenClaims, tools: list[Tool]) -> list[Tool]:
        allowed_tools, denied_tools, allowed_servers = self._get_user_permissions(user)

        if not allowed_tools and not user.roles:
            return []

        filtered = []
        for tool in tools:
            server_name = self._tool_index.get_tool_server(tool.name) or ""
            allowed, _ = self._is_tool_allowed(
                tool.name, server_name, allowed_tools, denied_tools, allowed_servers
            )
            if allowed:
                filtered.append(tool)

        logger.debug(
            "Filtered tools for '%s' (roles=%s): %d/%d",
            user.user_id, user.roles, len(filtered), len(tools),
        )
        return filtered
