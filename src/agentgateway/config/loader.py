"""YAML config loader for gateway.yaml, servers.yaml, roles.yaml."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from agentgateway.config.settings import AppSettings

logger = logging.getLogger(__name__)


# ── Server config models ──


class OBOConfig(BaseModel):
    enabled: bool = False
    token_endpoint: str | None = None


class ServerConfig(BaseModel):
    name: str
    transport: str  # "stdio", "streamable-http", "rest"
    command: str | None = None
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    url: str | None = None
    openapi_spec: str | None = None
    base_url: str | None = None
    obo: OBOConfig = Field(default_factory=OBOConfig)


class ServersConfig(BaseModel):
    servers: list[ServerConfig] = Field(default_factory=list)


# ── Role config models ──


class RoleConfig(BaseModel):
    description: str = ""
    allowed_tools: list[str] = Field(default_factory=list)
    denied_tools: list[str] = Field(default_factory=list)
    allowed_servers: list[str] = Field(default_factory=lambda: ["*"])


class RolesConfig(BaseModel):
    roles: dict[str, RoleConfig] = Field(default_factory=dict)


# ── Loaders ──


def _load_yaml(path: Path) -> dict[str, Any]:
    """Load a YAML file and return the parsed dict."""
    if not path.exists():
        logger.warning("Config file not found: %s — using defaults", path)
        return {}
    with open(path) as f:
        data = yaml.safe_load(f)
    return data if isinstance(data, dict) else {}


def load_gateway_settings(config_dir: Path) -> AppSettings:
    """Load gateway.yaml and merge into AppSettings."""
    raw = _load_yaml(config_dir / "gateway.yaml")
    return AppSettings(**raw)


def load_servers_config(config_dir: Path) -> ServersConfig:
    """Load servers.yaml into ServersConfig."""
    raw = _load_yaml(config_dir / "servers.yaml")
    return ServersConfig(**raw)


def load_roles_config(config_dir: Path) -> RolesConfig:
    """Load roles.yaml into RolesConfig."""
    raw = _load_yaml(config_dir / "roles.yaml")
    return RolesConfig(**raw)
