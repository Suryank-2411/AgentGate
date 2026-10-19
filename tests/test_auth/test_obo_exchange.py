"""Tests for OBO token exchange using the mock OAuth server."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agentgateway.auth.mock_oauth import router as oauth_router
from agentgateway.auth.obo_exchange import OBOTokenExchanger
from agentgateway.db.database import Database
from tests.conftest import create_test_jwt


@pytest.fixture
def mock_oauth_app() -> FastAPI:
    app = FastAPI()
    app.include_router(oauth_router)
    return app


@pytest.fixture
def mock_oauth_client(mock_oauth_app: FastAPI) -> TestClient:
    return TestClient(mock_oauth_app)


class TestMockOAuthServer:
    def test_discovery_endpoint(self, mock_oauth_client: TestClient):
        resp = mock_oauth_client.get("/oauth/.well-known/openid-configuration")
        assert resp.status_code == 200
        data = resp.json()
        assert "token_endpoint" in data
        assert "urn:ietf:params:oauth:grant-type:token-exchange" in data["grant_types_supported"]

    def test_jwks_endpoint(self, mock_oauth_client: TestClient):
        resp = mock_oauth_client.get("/oauth/jwks")
        assert resp.status_code == 200
        assert "keys" in resp.json()

    def test_obo_token_exchange(self, mock_oauth_client: TestClient):
        # Use the same secret as the mock OAuth server
        user_jwt = create_test_jwt(
            user_id="alice", roles=["developer"],
            secret="dev-secret-change-in-production",
        )
        resp = mock_oauth_client.post(
            "/oauth/token",
            data={
                "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
                "subject_token": user_jwt,
                "subject_token_type": "urn:ietf:params:oauth:token-type:jwt",
                "requested_token_type": "urn:ietf:params:oauth:token-type:access_token",
                "resource": "database-query",
                "client_id": "agentgateway",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["token_type"] == "Bearer"
        assert data["expires_in"] == 3600
        assert "obo:database-query" in data["scope"]

    def test_unsupported_grant_type(self, mock_oauth_client: TestClient):
        resp = mock_oauth_client.post(
            "/oauth/token", data={"grant_type": "client_credentials"}
        )
        assert resp.status_code == 400

    def test_invalid_subject_token(self, mock_oauth_client: TestClient):
        resp = mock_oauth_client.post(
            "/oauth/token",
            data={
                "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
                "subject_token": "invalid.token.here",
                "resource": "test",
            },
        )
        assert resp.status_code == 400
