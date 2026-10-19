"""Mock OAuth 2.0 server endpoints for demo and testing."""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import APIRouter, Form, Request
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/oauth", tags=["oauth"])

# Mock signing key (matches gateway's default dev secret)
MOCK_JWT_SECRET = "dev-secret-change-in-production"
MOCK_JWT_ALGORITHM = "HS256"


@router.get("/.well-known/openid-configuration")
async def openid_configuration(request: Request) -> JSONResponse:
    """Mock OIDC discovery endpoint."""
    base_url = str(request.base_url).rstrip("/")
    return JSONResponse({
        "issuer": "agentgateway",
        "authorization_endpoint": f"{base_url}/oauth/authorize",
        "token_endpoint": f"{base_url}/oauth/token",
        "jwks_uri": f"{base_url}/oauth/jwks",
        "grant_types_supported": [
            "authorization_code",
            "urn:ietf:params:oauth:grant-type:token-exchange",
        ],
        "subject_types_supported": ["public"],
        "id_token_signing_alg_values_supported": ["HS256", "RS256"],
    })


@router.get("/jwks")
async def jwks() -> JSONResponse:
    """Mock JWKS endpoint — returns empty for HS256 (symmetric key)."""
    return JSONResponse({"keys": []})


@router.post("/token")
async def token_exchange(
    grant_type: str = Form(...),
    subject_token: str = Form(None),
    subject_token_type: str = Form(None),
    requested_token_type: str = Form(None),
    resource: str = Form(None),
    client_id: str = Form(None),
    client_secret: str = Form(None),
) -> JSONResponse:
    """
    Mock token endpoint supporting RFC 8693 token exchange.

    In demo mode, this decodes the subject JWT and issues a new
    scoped token for the requested resource.
    """
    if grant_type == "urn:ietf:params:oauth:grant-type:token-exchange":
        return _handle_obo_exchange(subject_token, resource)

    return JSONResponse(
        {"error": "unsupported_grant_type", "error_description": f"Grant type '{grant_type}' not supported"},
        status_code=400,
    )


def _handle_obo_exchange(subject_token: str | None, resource: str | None) -> JSONResponse:
    """Handle OBO token exchange: validate subject, issue scoped token."""
    if not subject_token:
        return JSONResponse(
            {"error": "invalid_request", "error_description": "subject_token required"},
            status_code=400,
        )

    # Decode the subject token (allow expired for testing flexibility)
    try:
        payload = jwt.decode(
            subject_token,
            MOCK_JWT_SECRET,
            algorithms=[MOCK_JWT_ALGORITHM],
            options={"verify_exp": False, "verify_aud": False},
        )
    except jwt.InvalidTokenError as exc:
        return JSONResponse(
            {"error": "invalid_grant", "error_description": f"Invalid subject token: {exc}"},
            status_code=400,
        )

    # Issue a scoped downstream token
    now = datetime.now(timezone.utc)
    scoped_payload = {
        "sub": payload.get("sub", "unknown"),
        "roles": payload.get("roles", []),
        "email": payload.get("email"),
        "iss": "agentgateway",
        "aud": resource or "downstream",
        "iat": now,
        "exp": now + timedelta(hours=1),
        "scope": f"obo:{resource}",
        "original_sub": payload.get("sub"),
    }
    scoped_token = jwt.encode(scoped_payload, MOCK_JWT_SECRET, algorithm=MOCK_JWT_ALGORITHM)

    return JSONResponse({
        "access_token": scoped_token,
        "token_type": "Bearer",
        "expires_in": 3600,
        "issued_token_type": "urn:ietf:params:oauth:token-type:access_token",
        "scope": f"obo:{resource}",
    })
