"""Audit logging — writes structured tool invocation records to SQLite."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from agentgateway.db.database import Database

logger = logging.getLogger(__name__)


class AuditEntry(BaseModel):
    """A single audit log entry."""

    id: int | None = None
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    trace_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:16])
    user_id: str = "anonymous"
    user_roles: str = "[]"
    tool_name: str = ""
    server_name: str = ""
    arguments: str = "{}"
    result_summary: str = ""
    policy_decision: str = ""
    guardrail_violations: str = ""
    latency_ms: float = 0.0
    status: str = "success"


class AuditFilter(BaseModel):
    """Filtering options for querying audit logs."""

    user_id: str | None = None
    tool_name: str | None = None
    status: str | None = None
    limit: int = 100
    offset: int = 0


class AuditLogger:
    """Writes and queries audit log entries in SQLite."""

    def __init__(self, db: Database) -> None:
        self._db = db

    async def log_tool_call(
        self,
        user_id: str = "anonymous",
        user_roles: list[str] | None = None,
        tool_name: str = "",
        server_name: str = "",
        arguments: dict[str, Any] | None = None,
        result_summary: str = "",
        policy_decision: str = "",
        guardrail_violations: str = "",
        latency_ms: float = 0.0,
        status: str = "success",
    ) -> None:
        """Write an audit log entry."""
        entry = AuditEntry(
            user_id=user_id,
            user_roles=json.dumps(user_roles or []),
            tool_name=tool_name,
            server_name=server_name,
            arguments=json.dumps(self._sanitize_args(arguments or {})),
            result_summary=result_summary[:500],  # Truncate large results
            policy_decision=policy_decision,
            guardrail_violations=guardrail_violations,
            latency_ms=latency_ms,
            status=status,
        )
        await self._db.execute(
            "INSERT INTO audit_logs "
            "(trace_id, user_id, user_roles, tool_name, server_name, arguments, "
            "result_summary, policy_decision, guardrail_violations, latency_ms, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                entry.trace_id,
                entry.user_id,
                entry.user_roles,
                entry.tool_name,
                entry.server_name,
                entry.arguments,
                entry.result_summary,
                entry.policy_decision,
                entry.guardrail_violations,
                entry.latency_ms,
                entry.status,
            ),
        )
        logger.debug(
            "Audit: %s called %s on %s (status=%s, %.1fms)",
            user_id, tool_name, server_name, status, latency_ms,
        )

    async def query_logs(self, filters: AuditFilter | None = None) -> list[dict]:
        """Query audit logs with optional filtering."""
        if filters is None:
            filters = AuditFilter()

        conditions = []
        params: list[Any] = []

        if filters.user_id:
            conditions.append("user_id = ?")
            params.append(filters.user_id)
        if filters.tool_name:
            conditions.append("tool_name = ?")
            params.append(filters.tool_name)
        if filters.status:
            conditions.append("status = ?")
            params.append(filters.status)

        where = " AND ".join(conditions) if conditions else "1=1"
        sql = (
            f"SELECT * FROM audit_logs WHERE {where} "
            f"ORDER BY timestamp DESC LIMIT ? OFFSET ?"
        )
        params.extend([filters.limit, filters.offset])

        return await self._db.fetch_all(sql, tuple(params))

    @staticmethod
    def _sanitize_args(args: dict[str, Any]) -> dict[str, Any]:
        """Remove potentially sensitive values from arguments before logging."""
        sanitized = {}
        sensitive_keys = {"password", "secret", "token", "api_key", "credentials"}
        for key, value in args.items():
            if key.lower() in sensitive_keys:
                sanitized[key] = "***REDACTED***"
            elif isinstance(value, str) and len(value) > 1000:
                sanitized[key] = value[:200] + "...[truncated]"
            else:
                sanitized[key] = value
        return sanitized
