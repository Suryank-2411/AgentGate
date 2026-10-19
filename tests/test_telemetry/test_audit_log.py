"""Tests for audit logging."""

import pytest

from agentgateway.db.database import Database
from agentgateway.telemetry.audit_log import AuditFilter, AuditLogger


@pytest.fixture
async def audit_db(tmp_db_path: str):
    db = Database(tmp_db_path)
    await db.connect()
    yield db
    await db.disconnect()


@pytest.fixture
async def audit_logger(audit_db: Database) -> AuditLogger:
    return AuditLogger(audit_db)


class TestAuditLogger:
    async def test_log_successful_call(self, audit_logger: AuditLogger):
        await audit_logger.log_tool_call(
            user_id="alice",
            user_roles=["developer"],
            tool_name="list_files",
            server_name="file-manager",
            arguments={"directory": "/docs"},
            status="success",
            latency_ms=12.5,
        )
        logs = await audit_logger.query_logs()
        assert len(logs) == 1
        assert logs[0]["user_id"] == "alice"
        assert logs[0]["tool_name"] == "list_files"
        assert logs[0]["status"] == "success"

    async def test_log_denied_call(self, audit_logger: AuditLogger):
        await audit_logger.log_tool_call(
            user_id="bob",
            tool_name="delete_file",
            status="denied",
            policy_decision="Tool denied by RBAC",
        )
        logs = await audit_logger.query_logs(AuditFilter(status="denied"))
        assert len(logs) == 1
        assert logs[0]["policy_decision"] == "Tool denied by RBAC"

    async def test_log_multiple_and_filter(self, audit_logger: AuditLogger):
        await audit_logger.log_tool_call(user_id="alice", tool_name="list_files", status="success")
        await audit_logger.log_tool_call(user_id="bob", tool_name="execute_query", status="success")
        await audit_logger.log_tool_call(user_id="alice", tool_name="read_file", status="error")

        all_logs = await audit_logger.query_logs()
        assert len(all_logs) == 3

        alice_logs = await audit_logger.query_logs(AuditFilter(user_id="alice"))
        assert len(alice_logs) == 2

        tool_logs = await audit_logger.query_logs(AuditFilter(tool_name="execute_query"))
        assert len(tool_logs) == 1

    async def test_sensitive_args_redacted(self, audit_logger: AuditLogger):
        await audit_logger.log_tool_call(
            user_id="alice",
            tool_name="connect",
            arguments={"host": "db.local", "password": "super-secret", "api_key": "key123"},
        )
        logs = await audit_logger.query_logs()
        assert "super-secret" not in logs[0]["arguments"]
        assert "REDACTED" in logs[0]["arguments"]

    async def test_pagination(self, audit_logger: AuditLogger):
        for i in range(5):
            await audit_logger.log_tool_call(user_id=f"user{i}", tool_name="t", status="success")

        page1 = await audit_logger.query_logs(AuditFilter(limit=2, offset=0))
        page2 = await audit_logger.query_logs(AuditFilter(limit=2, offset=2))
        assert len(page1) == 2
        assert len(page2) == 2
        assert page1[0]["user_id"] != page2[0]["user_id"]
