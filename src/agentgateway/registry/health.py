"""Health check utilities for downstream servers."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agentgateway.registry.server_manager import ServerManager

logger = logging.getLogger(__name__)


async def check_all_servers(manager: ServerManager) -> dict[str, dict]:
    """Check health of all connected downstream servers."""
    results = {}
    for name in manager.connected_servers:
        try:
            client = manager.get_client(name)
            # A simple list_tools call as health check
            await client.list_tools()
            results[name] = {"status": "healthy"}
        except Exception as exc:
            results[name] = {"status": "unhealthy", "error": str(exc)}
            logger.warning("Health check failed for '%s': %s", name, exc)
    return results
