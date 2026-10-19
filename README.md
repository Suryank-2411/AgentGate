# AgentGateWay — Secure Enterprise MCP Gateway & Policy Proxy

An enterprise-grade, lightweight MCP Gateway proxy written in Python that sits between AI clients (like Claude Desktop, Cursor, or LangChain agents) and internal MCP tools. It enforces zero-trust identity delegation (OAuth2 OBO), dynamic tool filtering, fine-grained RBAC, and real-time prompt-injection defense.

## Quick Start

```bash
# Install dependencies
pip install -e ".[dev]"

# Start the gateway
uvicorn agentgateway.main:app --reload

# Check health
curl http://localhost:8000/health
```

Full documentation below.
