#!/usr/bin/env bash
# AgentGateWay Demo Script
# Generates test JWTs and demonstrates key gateway scenarios.
#
# Prerequisites: pip install -e ".[dev]"
# The gateway must be running: uvicorn agentgateway.main:app

set -euo pipefail

GATEWAY_URL="${GATEWAY_URL:-http://localhost:8000}"
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
NC='\033[0m' # No Color

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║           AgentGateWay — Demo Script                        ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

# Helper: generate JWTs using Python
generate_jwt() {
    local user_id="$1"
    local roles="$2"
    python3 -c "
import sys; sys.path.insert(0, 'src'); sys.path.insert(0, '.')
from tests.conftest import create_test_jwt
token = create_test_jwt(user_id='$user_id', roles=$roles, secret='dev-secret-change-in-production')
print(token)
"
}

echo -e "${YELLOW}[1] Health Check${NC}"
echo "  curl $GATEWAY_URL/health"
curl -s "$GATEWAY_URL/health" | python3 -m json.tool
echo ""

echo -e "${YELLOW}[2] Admin: List All Tools${NC}"
echo "  curl $GATEWAY_URL/admin/tools"
curl -s "$GATEWAY_URL/admin/tools" | python3 -m json.tool
echo ""

echo -e "${YELLOW}[3] Admin: List Connected Servers${NC}"
echo "  curl $GATEWAY_URL/admin/servers"
curl -s "$GATEWAY_URL/admin/servers" | python3 -m json.tool
echo ""

echo -e "${YELLOW}[4] Admin: Audit Logs${NC}"
echo "  curl $GATEWAY_URL/admin/audit"
curl -s "$GATEWAY_URL/admin/audit?limit=5" | python3 -m json.tool
echo ""

echo -e "${YELLOW}[5] Mock OAuth: OIDC Discovery${NC}"
echo "  curl $GATEWAY_URL/oauth/.well-known/openid-configuration"
curl -s "$GATEWAY_URL/oauth/.well-known/openid-configuration" | python3 -m json.tool
echo ""

echo -e "${GREEN}--- Generating Test JWTs ---${NC}"
ADMIN_JWT=$(generate_jwt "admin-user" "['admin']")
DEV_JWT=$(generate_jwt "dev-user" "['developer']")
ANALYST_JWT=$(generate_jwt "analyst-user" "['analyst']")
echo "  Admin JWT:    ${ADMIN_JWT:0:50}..."
echo "  Developer JWT: ${DEV_JWT:0:50}..."
echo "  Analyst JWT:   ${ANALYST_JWT:0:50}..."
echo ""

echo -e "${YELLOW}[6] OBO Token Exchange${NC}"
echo "  POST $GATEWAY_URL/oauth/token"
curl -s -X POST "$GATEWAY_URL/oauth/token" \
    -d "grant_type=urn:ietf:params:oauth:grant-type:token-exchange" \
    -d "subject_token=$DEV_JWT" \
    -d "resource=database-query" \
    -d "client_id=agentgateway" | python3 -m json.tool
echo ""

echo -e "${GREEN}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║  Demo complete! Connect to the MCP endpoint at:            ║${NC}"
echo -e "${GREEN}║  $GATEWAY_URL/mcp                                ║${NC}"
echo -e "${GREEN}║                                                            ║${NC}"
echo -e "${GREEN}║  Use 'mcp dev' or MCP Inspector to test tool calls.        ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════════════════╝${NC}"
