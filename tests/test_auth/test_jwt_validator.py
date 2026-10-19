"""Tests for JWT validation."""

from datetime import timedelta

import jwt as pyjwt
import pytest

from agentgateway.auth.jwt_validator import JWTValidator, TokenClaims
from agentgateway.config.settings import AuthSettings
from tests.conftest import TEST_JWT_ALGORITHM, TEST_JWT_SECRET, create_test_jwt


@pytest.fixture
def validator() -> JWTValidator:
    return JWTValidator(
        AuthSettings(
            jwt_secret=TEST_JWT_SECRET,
            jwt_algorithm=TEST_JWT_ALGORITHM,
            jwt_issuer="agentgateway",
            jwt_audience="agentgateway",
        )
    )


class TestJWTValidator:
    def test_valid_token(self, validator: JWTValidator):
        token = create_test_jwt(user_id="alice", roles=["developer"], email="alice@co.com")
        claims = validator.validate(token)
        assert claims.user_id == "alice"
        assert claims.roles == ["developer"]
        assert claims.email == "alice@co.com"
        assert claims.raw_token == token

    def test_multiple_roles(self, validator: JWTValidator):
        token = create_test_jwt(user_id="bob", roles=["admin", "developer"])
        claims = validator.validate(token)
        assert set(claims.roles) == {"admin", "developer"}

    def test_expired_token_raises(self, validator: JWTValidator):
        token = create_test_jwt(expires_delta=timedelta(seconds=-10))
        with pytest.raises(pyjwt.ExpiredSignatureError):
            validator.validate(token)

    def test_wrong_secret_raises(self, validator: JWTValidator):
        token = create_test_jwt(secret="wrong-secret")
        with pytest.raises(pyjwt.InvalidSignatureError):
            validator.validate(token)

    def test_malformed_token_raises(self, validator: JWTValidator):
        with pytest.raises(pyjwt.DecodeError):
            validator.validate("not.a.jwt")

    def test_missing_required_claims(self, validator: JWTValidator):
        # Token without 'sub' claim
        token = pyjwt.encode(
            {"roles": ["admin"], "exp": 9999999999, "iss": "agentgateway", "aud": "agentgateway"},
            TEST_JWT_SECRET,
            algorithm=TEST_JWT_ALGORITHM,
        )
        with pytest.raises(pyjwt.MissingRequiredClaimError):
            validator.validate(token)

    def test_extract_bearer_token(self):
        assert JWTValidator.extract_bearer_token("Bearer abc123") == "abc123"
        assert JWTValidator.extract_bearer_token("bearer xyz") == "xyz"
        assert JWTValidator.extract_bearer_token("Basic abc") is None
        assert JWTValidator.extract_bearer_token(None) is None
        assert JWTValidator.extract_bearer_token("") is None
