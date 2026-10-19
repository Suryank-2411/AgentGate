"""Pydantic settings for AgentGateWay, loaded from env vars and gateway.yaml."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings


class AuthSettings(BaseModel):
    enabled: bool = False
    jwt_algorithm: str = "HS256"
    jwt_secret: str = "dev-secret-change-in-production"
    jwt_issuer: str = "agentgateway"
    jwt_audience: str = "agentgateway"
    jwt_jwks_url: str | None = None


class PolicySettings(BaseModel):
    engine: str = "local"  # "local" or "opa"
    opa_url: str = "http://localhost:8181"


class DatabaseSettings(BaseModel):
    path: str = "data/agentgateway.db"


class GuardrailsSettings(BaseModel):
    enabled: bool = True
    block_sql_injection: bool = True
    block_path_traversal: bool = True
    detect_pii: bool = True
    detect_prompt_injection: bool = True


class TelemetrySettings(BaseModel):
    audit_enabled: bool = True
    otel_enabled: bool = False
    otel_endpoint: str = "http://localhost:4317"


class MockOAuthSettings(BaseModel):
    enabled: bool = True


class GatewaySettings(BaseModel):
    host: str = "127.0.0.1"
    port: int = 8000
    log_level: str = "INFO"


class AppSettings(BaseSettings):
    """Root settings — merges env vars with YAML config."""

    gateway: GatewaySettings = Field(default_factory=GatewaySettings)
    auth: AuthSettings = Field(default_factory=AuthSettings)
    policy: PolicySettings = Field(default_factory=PolicySettings)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    guardrails: GuardrailsSettings = Field(default_factory=GuardrailsSettings)
    telemetry: TelemetrySettings = Field(default_factory=TelemetrySettings)
    mock_oauth: MockOAuthSettings = Field(default_factory=MockOAuthSettings)
    config_dir: str = "config"

    model_config = {"env_prefix": "AGW_", "env_nested_delimiter": "__"}


def resolve_config_dir(settings: AppSettings) -> Path:
    """Return the absolute path to the config directory."""
    config_path = Path(settings.config_dir)
    if not config_path.is_absolute():
        config_path = Path.cwd() / config_path
    return config_path
