"""Tests for SQLite database layer."""

import pytest

from agentgateway.db.database import Database


@pytest.fixture
async def test_db(tmp_db_path: str):
    db = Database(tmp_db_path)
    await db.connect()
    yield db
    await db.disconnect()


class TestDatabase:
    async def test_schema_created(self, test_db: Database):
        """Verify audit_logs and token_cache tables exist."""
        rows = await test_db.fetch_all(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        table_names = [r["name"] for r in rows]
        assert "audit_logs" in table_names
        assert "token_cache" in table_names

    async def test_insert_audit_log(self, test_db: Database):
        await test_db.execute(
            "INSERT INTO audit_logs (user_id, tool_name, server_name, status) VALUES (?, ?, ?, ?)",
            ("alice", "list_files", "file-manager", "success"),
        )
        rows = await test_db.fetch_all("SELECT * FROM audit_logs")
        assert len(rows) == 1
        assert rows[0]["user_id"] == "alice"
        assert rows[0]["tool_name"] == "list_files"
        assert rows[0]["status"] == "success"
        assert rows[0]["timestamp"] is not None

    async def test_insert_token_cache(self, test_db: Database):
        await test_db.execute(
            "INSERT INTO token_cache (user_id, target_server, access_token, expires_at) "
            "VALUES (?, ?, ?, ?)",
            ("bob", "database-query", "tok_abc123", "2099-01-01T00:00:00Z"),
        )
        row = await test_db.fetch_one(
            "SELECT * FROM token_cache WHERE user_id = ?", ("bob",)
        )
        assert row is not None
        assert row["target_server"] == "database-query"
        assert row["access_token"] == "tok_abc123"

    async def test_fetch_one_missing(self, test_db: Database):
        row = await test_db.fetch_one(
            "SELECT * FROM audit_logs WHERE user_id = ?", ("nonexistent",)
        )
        assert row is None

    async def test_disconnect_and_reconnect(self, tmp_db_path: str):
        db = Database(tmp_db_path)
        await db.connect()
        await db.execute(
            "INSERT INTO audit_logs (user_id, tool_name, status) VALUES (?, ?, ?)",
            ("test", "t", "success"),
        )
        await db.disconnect()

        # Reconnect and verify data persisted
        db2 = Database(tmp_db_path)
        await db2.connect()
        rows = await db2.fetch_all("SELECT * FROM audit_logs")
        assert len(rows) == 1
        await db2.disconnect()

    async def test_not_connected_raises(self):
        db = Database("/tmp/never_connected.db")
        with pytest.raises(RuntimeError, match="not connected"):
            db.conn
