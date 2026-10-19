"""Shared test fixtures for AgentGateWay."""

from __future__ import annotations

import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt
import pytest

# Point config to the project's config directory
os.environ.setdefault("AGW_CONFIG_DIR", str(Path(__file__).parent.parent / "config"))


@pytest.fixture
def config_dir() -> Path:
    return Path(__file__).parent.parent / "config"


@pytest.fixture
def tmp_db_path(tmp_path: Path) -> str:
    return str(tmp_path / "test.db")


@pytest.fixture
def tmp_config_dir(tmp_path: Path) -> Path:
    """Create a temporary config directory with sample files."""
    cfg = tmp_path / "config"
    cfg.mkdir()
    (cfg / "gateway.yaml").write_text(
        "gateway:\n  host: '0.0.0.0'\n  port: 9999\n  log_level: DEBUG\n"
        "auth:\n  enabled: false\n"
        "database:\n  path: ':memory:'\n"
    )
    (cfg / "servers.yaml").write_text("servers: []\n")
    (cfg / "roles.yaml").write_text(
        "roles:\n  admin:\n    allowed_tools: ['*']\n"
    )
    return cfg


# ── JWT test helpers ──

TEST_JWT_SECRET = "test-secret-key-for-testing-only"
TEST_JWT_ALGORITHM = "HS256"


def create_test_jwt(
    user_id: str = "test-user",
    roles: list[str] | None = None,
    email: str | None = "test@example.com",
    expires_delta: timedelta | None = None,
    secret: str = TEST_JWT_SECRET,
) -> str:
    """Generate a signed JWT for testing."""
    if roles is None:
        roles = ["developer"]
    if expires_delta is None:
        expires_delta = timedelta(hours=1)

    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "roles": roles,
        "email": email,
        "iss": "agentgateway",
        "aud": "agentgateway",
        "iat": now,
        "exp": now + expires_delta,
    }
    return jwt.encode(payload, secret, algorithm=TEST_JWT_ALGORITHM)


@pytest.fixture
def test_jwt() -> str:
    return create_test_jwt()


@pytest.fixture
def admin_jwt() -> str:
    return create_test_jwt(user_id="admin-user", roles=["admin"])


@pytest.fixture
def analyst_jwt() -> str:
    return create_test_jwt(user_id="analyst-user", roles=["analyst"])
