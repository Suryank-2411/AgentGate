"""Tests for config loading and settings."""

from pathlib import Path

import pytest

from agentgateway.config.loader import load_gateway_settings, load_roles_config, load_servers_config
from agentgateway.config.settings import AppSettings


class TestAppSettings:
    def test_default_settings(self):
        s = AppSettings()
        assert s.gateway.host == "127.0.0.1"
        assert s.gateway.port == 8000
        assert s.auth.enabled is False
        assert s.policy.engine == "local"
        assert s.database.path == "data/agentgateway.db"

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("AGW_AUTH__ENABLED", "true")
        monkeypatch.setenv("AGW_GATEWAY__PORT", "9999")
        s = AppSettings()
        assert s.auth.enabled is True
        assert s.gateway.port == 9999


class TestConfigLoader:
    def test_load_gateway_settings(self, config_dir: Path):
        s = load_gateway_settings(config_dir)
        assert s.gateway.host == "127.0.0.1"
        assert s.gateway.port == 8000
        assert s.gateway.log_level == "INFO"

    def test_load_servers_config(self, config_dir: Path):
        cfg = load_servers_config(config_dir)
        assert len(cfg.servers) >= 2
        names = [s.name for s in cfg.servers]
        assert "file-manager" in names
        assert "database-query" in names

    def test_load_roles_config(self, config_dir: Path):
        cfg = load_roles_config(config_dir)
        assert "admin" in cfg.roles
        assert "developer" in cfg.roles
        assert "analyst" in cfg.roles
        assert cfg.roles["admin"].allowed_tools == ["*"]
        assert "delete_file" in cfg.roles["developer"].denied_tools

    def test_load_from_tmp_config(self, tmp_config_dir: Path):
        s = load_gateway_settings(tmp_config_dir)
        assert s.gateway.host == "0.0.0.0"
        assert s.gateway.port == 9999

    def test_missing_config_returns_defaults(self, tmp_path: Path):
        cfg = load_servers_config(tmp_path)
        assert cfg.servers == []
