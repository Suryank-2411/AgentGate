"""Policy engine abstract interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from pydantic import BaseModel

if TYPE_CHECKING:
    from mcp.types import Tool

    from agentgateway.auth.jwt_validator import TokenClaims


class PolicyDecision(BaseModel):
    """Result of a policy evaluation."""

    allowed: bool
    reason: str | None = None


class PolicyEngine(ABC):
    """Abstract base class for authorization policy engines."""

    @abstractmethod
    async def check_tool_access(
        self, user: TokenClaims, tool_name: str, server_name: str
    ) -> PolicyDecision:
        """Check if a user is authorized to call a specific tool."""
        ...

    @abstractmethod
    async def check_payload(
        self, user: TokenClaims, tool_name: str, arguments: dict
    ) -> PolicyDecision:
        """Check if tool arguments pass payload-level policy checks."""
        ...

    @abstractmethod
    async def filter_tools(self, user: TokenClaims, tools: list[Tool]) -> list[Tool]:
        """Filter the tool list to only those the user is authorized to see."""
        ...
