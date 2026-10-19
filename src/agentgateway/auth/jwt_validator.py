"""JWT token validation and identity extraction."""

from __future__ import annotations

import logging
from typing import Any

import jwt
from pydantic import BaseModel

from agentgateway.config.settings import AuthSettings

logger = logging.getLogger(__name__)


class TokenClaims(BaseModel):
    """Parsed identity claims from a validated JWT."""

    user_id: str
    roles: list[str] = []
    email: str | None = None
    raw_token: str = ""  # Original token for OBO exchange


class JWTValidator:
    """Validates JWT tokens and extracts identity claims."""

    def __init__(self, settings: AuthSettings) -> None:
        self._algorithm = settings.jwt_algorithm
        self._secret = settings.jwt_secret
        self._issuer = settings.jwt_issuer
        self._audience = settings.jwt_audience
        self._jwks_url = settings.jwt_jwks_url

    def validate(self, token: str) -> TokenClaims:
        """
        Validate a JWT token and return parsed claims.

        Raises jwt.PyJWTError on validation failure.
        """
        try:
            payload = jwt.decode(
                token,
                self._secret,
                algorithms=[self._algorithm],
                issuer=self._issuer,
                audience=self._audience,
                options={
                    "require": ["sub", "exp", "iss"],
                    "verify_exp": True,
                    "verify_iss": True,
                    "verify_aud": True,
                },
            )
        except jwt.ExpiredSignatureError:
            logger.warning("JWT expired")
            raise
        except jwt.InvalidTokenError as exc:
            logger.warning("JWT validation failed: %s", exc)
            raise

        return TokenClaims(
            user_id=payload.get("sub", "unknown"),
            roles=payload.get("roles", []),
            email=payload.get("email"),
            raw_token=token,
        )

    @staticmethod
    def extract_bearer_token(authorization: str | None) -> str | None:
        """Extract the token from an 'Authorization: Bearer <token>' header."""
        if not authorization:
            return None
        parts = authorization.split(" ", 1)
        if len(parts) == 2 and parts[0].lower() == "bearer":
            return parts[1]
        return None
