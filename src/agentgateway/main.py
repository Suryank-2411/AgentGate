"""AgentGateWay — FastAPI application entry point.

Wires together all gateway subsystems:
  Auth → Policy → Guardrails → Proxy → Audit
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse
from starlette.routing import Mount

from agentgateway.auth.jwt_validator import JWTValidator
from agentgateway.auth.mock_oauth import router as oauth_router
from agentgateway.config.loader import load_gateway_settings, load_roles_config, load_servers_config
from agentgateway.config.settings import AppSettings, resolve_config_dir
from agentgateway.db.database import Database
from agentgateway.guardrails.sanitizer import Sanitizer
from agentgateway.policy.engine import PolicyEngine
from agentgateway.policy.local_engine import LocalPolicyEngine
from agentgateway.policy.opa_engine import OPAPolicyEngine
from agentgateway.proxy.gateway_server import GatewayServer
from agentgateway.proxy.rest_virtualizer import RESTVirtualizer
from agentgateway.registry.health import check_all_servers
from agentgateway.registry.server_manager import ServerManager
from agentgateway.registry.tool_index import ToolIndex
from agentgateway.telemetry.audit_log import AuditFilter, AuditLogger
from agentgateway.telemetry.otel import GatewayTracer

logger = logging.getLogger(__name__)


def _configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def _load_settings() -> AppSettings:
    env_settings = AppSettings()
    config_dir = resolve_config_dir(env_settings)
    if (config_dir / "gateway.yaml").exists():
        return load_gateway_settings(config_dir)
    return env_settings


# ── Shared application state ──

settings: AppSettings = _load_settings()
config_dir: Path = resolve_config_dir(settings)
db: Database = Database(settings.database.path)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan — startup and shutdown hooks."""
    _configure_logging(settings.gateway.log_level)
    logger.info("AgentGateWay starting up")
    logger.info("Config dir: %s", config_dir)

    async with AsyncExitStack() as stack:
        # 1. Initialize database
        await db.connect()

        # 2. Load sub-configs
        servers_cfg = load_servers_config(config_dir)
        roles_cfg = load_roles_config(config_dir)
        logger.info(
            "Loaded %d server(s), %d role(s)",
            len(servers_cfg.servers), len(roles_cfg.roles),
        )

        # 3. Build tool index and server manager
        tool_index = ToolIndex()
        server_manager = ServerManager(servers_cfg.servers, tool_index)
        await server_manager.start()

        # 4. REST virtualization
        rest_virtualizer = RESTVirtualizer()
        for srv in servers_cfg.servers:
            if srv.transport == "rest" and srv.openapi_spec and srv.base_url:
                spec_path = str(config_dir / srv.openapi_spec) if not Path(srv.openapi_spec).is_absolute() else srv.openapi_spec
                tools = rest_virtualizer.load_spec(spec_path, srv.base_url, srv.name)
                for tool in tools:
                    tool_index.register(tool, srv.name)

        # 5. Build policy engine
        policy_engine: PolicyEngine
        if settings.policy.engine == "opa":
            policy_engine = OPAPolicyEngine(settings.policy.opa_url, tool_index)
            logger.info("Using OPA policy engine at %s", settings.policy.opa_url)
        else:
            policy_engine = LocalPolicyEngine(roles_cfg, tool_index)
            logger.info("Using local RBAC policy engine")

        # 6. Build guardrails
        sanitizer = Sanitizer(settings.guardrails)

        # 7. Build audit logger and tracer
        audit_logger = AuditLogger(db)
        tracer = GatewayTracer(
            enabled=settings.telemetry.otel_enabled,
            endpoint=settings.telemetry.otel_endpoint if settings.telemetry.otel_enabled else None,
        )

        # 8. Build JWT validator
        jwt_validator = JWTValidator(settings.auth)

        # 9. Build gateway MCP server and wire subsystems
        gateway = GatewayServer(tool_index, server_manager)
        gateway.policy_engine = policy_engine
        gateway.sanitizer = sanitizer
        gateway.audit_logger = audit_logger
        gateway.tracer = tracer
        gateway.rest_virtualizer = rest_virtualizer

        if settings.auth.enabled:
            gateway.auth_extractor = lambda ctx: None  # Placeholder — JWT extracted at HTTP layer

        # 10. Mount the MCP server
        mcp_app = gateway.server.streamable_http_app()
        _app.mount("/mcp", app=mcp_app)

        # Enter session manager lifecycle
        await stack.enter_async_context(gateway.server.session_manager.run())

        # Store state on app for access by admin endpoints
        _app.state.settings = settings
        _app.state.db = db
        _app.state.tool_index = tool_index
        _app.state.server_manager = server_manager
        _app.state.policy_engine = policy_engine
        _app.state.audit_logger = audit_logger
        _app.state.gateway = gateway
        _app.state.jwt_validator = jwt_validator
        _app.state.rest_virtualizer = rest_virtualizer

        logger.info(
            "AgentGateWay ready — %d tools from %d servers",
            tool_index.tool_count, tool_index.server_count,
        )

        yield

        # Shutdown
        await server_manager.stop()
        if isinstance(policy_engine, OPAPolicyEngine):
            await policy_engine.close()
        await rest_virtualizer.close()
        await db.disconnect()
        logger.info("AgentGateWay shut down")


app = FastAPI(
    title="AgentGateWay",
    description="Secure Enterprise MCP Gateway & Policy Proxy",
    version="0.1.0",
    lifespan=lifespan,
)

# Mount mock OAuth endpoints if enabled
if settings.mock_oauth.enabled:
    app.include_router(oauth_router)


# ── Admin & Health Endpoints ──


@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse({"status": "ok", "version": "0.1.0"})


@app.get("/admin/tools")
async def admin_tools() -> JSONResponse:
    """List all tools registered in the gateway."""
    tool_index: ToolIndex = app.state.tool_index
    tools = []
    for tool in tool_index.get_all_tools():
        tools.append({
            "name": tool.name,
            "description": tool.description,
            "server": tool_index.get_tool_server(tool.name),
        })
    return JSONResponse({"tools": tools, "total": len(tools)})


@app.get("/admin/servers")
async def admin_servers() -> JSONResponse:
    """List all connected downstream servers."""
    manager: ServerManager = app.state.server_manager
    servers = []
    for name in manager.connected_servers:
        tool_index: ToolIndex = app.state.tool_index
        tools = tool_index.get_tools_by_server(name)
        servers.append({
            "name": name,
            "healthy": manager.is_healthy(name),
            "tool_count": len(tools),
        })
    return JSONResponse({"servers": servers})


@app.get("/admin/health-check")
async def admin_health_check() -> JSONResponse:
    """Run health checks on all downstream servers."""
    manager: ServerManager = app.state.server_manager
    results = await check_all_servers(manager)
    return JSONResponse(results)


@app.get("/admin/audit")
async def admin_audit(
    user_id: str | None = None,
    tool_name: str | None = None,
    status: str | None = None,
    limit: int = Query(default=50, le=500),
    offset: int = Query(default=0, ge=0),
) -> JSONResponse:
    """Query audit logs."""
    audit_logger: AuditLogger = app.state.audit_logger
    logs = await audit_logger.query_logs(
        AuditFilter(
            user_id=user_id,
            tool_name=tool_name,
            status=status,
            limit=limit,
            offset=offset,
        )
    )
    return JSONResponse({"logs": logs, "count": len(logs)})
