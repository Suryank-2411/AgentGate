"""Gateway MCP server — exposes downstream tools to AI clients via proxy."""

from __future__ import annotations

import logging
import time
from typing import Any

from mcp.server.lowlevel.server import Server
from mcp.types import (
    CallToolRequestParams,
    CallToolResult,
    ListToolsResult,
    PaginatedRequestParams,
    TextContent,
    Tool,
)

from agentgateway.registry.server_manager import ServerManager
from agentgateway.registry.tool_index import ToolIndex

logger = logging.getLogger(__name__)


class GatewayServer:
    """
    MCP proxy server that dynamically exposes tools from downstream servers.

    Uses the low-level Server API for full control over tools/list and tools/call.
    """

    def __init__(
        self,
        tool_index: ToolIndex,
        server_manager: ServerManager,
    ) -> None:
        self._tool_index = tool_index
        self._server_manager = server_manager
        self._server = Server("AgentGateWay")

        # Pluggable hooks — set by main.py after constructing subsystems
        self.policy_engine: Any = None
        self.sanitizer: Any = None
        self.audit_logger: Any = None
        self.obo_exchanger: Any = None
        self.tracer: Any = None
        self.auth_extractor: Any = None  # callable(ctx) -> TokenClaims | None

        self._register_handlers()

    @property
    def server(self) -> Server:
        return self._server

    def _register_handlers(self) -> None:
        """Register JSON-RPC handlers for MCP protocol methods."""
        self._server.add_request_handler(
            "tools/list", PaginatedRequestParams, self._handle_list_tools
        )
        self._server.add_request_handler(
            "tools/call", CallToolRequestParams, self._handle_call_tool
        )

    async def _handle_list_tools(self, ctx: Any, params: PaginatedRequestParams) -> ListToolsResult:
        """Return all discovered tools, optionally filtered by policy."""
        tools = self._tool_index.get_all_tools()

        # Policy-based filtering (wired in Task 6)
        if self.policy_engine and self.auth_extractor:
            claims = self.auth_extractor(ctx)
            if claims:
                tools = await self.policy_engine.filter_tools(claims, tools)

        logger.debug("tools/list: returning %d tools", len(tools))
        return ListToolsResult(tools=tools)

    async def _handle_call_tool(self, ctx: Any, params: CallToolRequestParams) -> CallToolResult:
        """Route a tool call through the gateway pipeline."""
        tool_name = params.name
        arguments = params.arguments or {}
        start = time.monotonic()
        claims = None

        # 1. Auth extraction (wired in Task 5)
        if self.auth_extractor:
            claims = self.auth_extractor(ctx)

        # 2. Policy check (wired in Task 6)
        if self.policy_engine and claims:
            server_name = self._tool_index.get_tool_server(tool_name) or ""
            decision = await self.policy_engine.check_tool_access(claims, tool_name, server_name)
            if not decision.allowed:
                return self._denied_result(tool_name, decision.reason or "Access denied by policy")

        # 3. Guardrails check (wired in Task 7)
        if self.sanitizer:
            san_result = self.sanitizer.check_input(tool_name, arguments)
            if not san_result.passed:
                violations_str = "; ".join(v.message for v in san_result.violations if v.severity == "block")
                return self._denied_result(tool_name, f"Blocked by guardrails: {violations_str}")

        # 4. Proxy the call to downstream
        result = await self._proxy_tool_call(tool_name, arguments, start)

        # 5. Output guardrails (wired in Task 7)
        if self.sanitizer and not result.is_error:
            out_result = self.sanitizer.check_output(tool_name, result)
            if not out_result.passed:
                for v in out_result.violations:
                    logger.warning("Output guardrail: %s on %s", v.message, tool_name)

        # 6. Audit log (wired in Task 9)
        if self.audit_logger:
            elapsed = (time.monotonic() - start) * 1000
            await self.audit_logger.log_tool_call(
                user_id=claims.user_id if claims else "anonymous",
                user_roles=claims.roles if claims else [],
                tool_name=tool_name,
                server_name=self._tool_index.get_tool_server(tool_name) or "unknown",
                arguments=arguments,
                status="error" if result.is_error else "success",
                latency_ms=elapsed,
            )

        return result

    async def _proxy_tool_call(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        start: float,
    ) -> CallToolResult:
        """Route a tool call to the correct downstream server."""
        server_name = self._tool_index.get_tool_server(tool_name)
        if server_name is None:
            return CallToolResult(
                content=[TextContent(type="text", text=f"Unknown tool: {tool_name}")],
                is_error=True,
            )

        try:
            client = self._server_manager.get_client(server_name)
        except KeyError:
            return CallToolResult(
                content=[TextContent(
                    type="text",
                    text=f"Server '{server_name}' for tool '{tool_name}' is not connected",
                )],
                is_error=True,
            )

        try:
            result = await client.call_tool(tool_name, arguments)
            elapsed = (time.monotonic() - start) * 1000
            logger.info(
                "Proxied %s → %s (%.1fms, error=%s)",
                tool_name, server_name, elapsed, result.is_error,
            )
            return CallToolResult(
                content=list(result.content),
                structured_content=result.structured_content,
                is_error=result.is_error,
            )
        except Exception as exc:
            elapsed = (time.monotonic() - start) * 1000
            logger.error("Proxy error %s → %s (%.1fms): %s", tool_name, server_name, elapsed, exc)
            return CallToolResult(
                content=[TextContent(type="text", text=f"Gateway proxy error: {exc}")],
                is_error=True,
            )

    @staticmethod
    def _denied_result(tool_name: str, reason: str) -> CallToolResult:
        return CallToolResult(
            content=[TextContent(type="text", text=f"Access denied for '{tool_name}': {reason}")],
            is_error=True,
        )
