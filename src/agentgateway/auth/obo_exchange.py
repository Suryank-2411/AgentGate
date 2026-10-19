"""OAuth 2.0 On-Behalf-Of (OBO) token exchange — RFC 8693."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

import httpx

from agentgateway.db.database import Database

logger = logging.getLogger(__name__)

TOKEN_EXCHANGE_GRANT = "urn:ietf:params:oauth:grant-type:token-exchange"
JWT_TOKEN_TYPE = "urn:ietf:params:oauth:token-type:jwt"
ACCESS_TOKEN_TYPE = "urn:ietf:params:oauth:token-type:access_token"


class OBOTokenExchanger:
    """
    Performs OAuth 2.0 Token Exchange (RFC 8693) to delegate
    the user's identity to downstream services.
    """

    def __init__(
        self,
        token_endpoint: str,
        client_id: str = "agentgateway",
        client_secret: str = "",
        db: Database | None = None,
    ) -> None:
        self._token_endpoint = token_endpoint
        self._client_id = client_id
        self._client_secret = client_secret
        self._db = db
        self._http = httpx.AsyncClient(timeout=10.0)

    async def exchange(self, user_jwt: str, target_server: str) -> str:
        """
        Exchange a user JWT for a scoped downstream token.

        Checks the SQLite cache first. On cache miss, performs
        the RFC 8693 token exchange against the configured endpoint.
        """
        # Check cache
        cached = await self._get_cached_token(user_jwt, target_server)
        if cached:
            logger.debug("OBO cache hit for target '%s'", target_server)
            return cached

        # Perform token exchange
        logger.info("OBO exchange for target '%s'", target_server)
        response = await self._http.post(
            self._token_endpoint,
            data={
                "grant_type": TOKEN_EXCHANGE_GRANT,
                "subject_token": user_jwt,
                "subject_token_type": JWT_TOKEN_TYPE,
                "requested_token_type": ACCESS_TOKEN_TYPE,
                "resource": target_server,
                "client_id": self._client_id,
                "client_secret": self._client_secret,
            },
        )
        response.raise_for_status()
        data = response.json()

        access_token = data["access_token"]
        expires_in = data.get("expires_in", 3600)

        # Cache the token
        await self._cache_token(user_jwt, target_server, access_token, expires_in)

        return access_token

    async def _get_cached_token(self, user_jwt: str, target_server: str) -> str | None:
        """Look up a cached OBO token that hasn't expired."""
        if not self._db:
            return None

        # Use a hash of the JWT as user_id for cache key
        import hashlib

        user_key = hashlib.sha256(user_jwt.encode()).hexdigest()[:16]

        row = await self._db.fetch_one(
            "SELECT access_token, expires_at FROM token_cache "
            "WHERE user_id = ? AND target_server = ?",
            (user_key, target_server),
        )
        if not row:
            return None

        expires_at = datetime.fromisoformat(row["expires_at"])
        if expires_at <= datetime.now(timezone.utc):
            # Expired — delete and return None
            await self._db.execute(
                "DELETE FROM token_cache WHERE user_id = ? AND target_server = ?",
                (user_key, target_server),
            )
            return None

        return row["access_token"]

    async def _cache_token(
        self, user_jwt: str, target_server: str, token: str, expires_in: int
    ) -> None:
        """Cache an OBO token in SQLite."""
        if not self._db:
            return

        import hashlib
        from datetime import timedelta

        user_key = hashlib.sha256(user_jwt.encode()).hexdigest()[:16]
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

        await self._db.execute(
            "INSERT OR REPLACE INTO token_cache (user_id, target_server, access_token, expires_at) "
            "VALUES (?, ?, ?, ?)",
            (user_key, target_server, token, expires_at.isoformat()),
        )

    async def close(self) -> None:
        await self._http.aclose()
