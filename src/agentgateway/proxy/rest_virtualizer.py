"""REST-to-MCP Virtualization — converts OpenAPI specs into MCP tools."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

import httpx
import yaml
from mcp.types import Tool

logger = logging.getLogger(__name__)


class VirtualEndpoint:
    """A single REST endpoint virtualized as an MCP tool."""

    def __init__(
        self,
        tool_name: str,
        method: str,
        path_template: str,
        base_url: str,
        summary: str = "",
        description: str = "",
        path_params: list[dict] = None,
        query_params: list[dict] = None,
        body_schema: dict | None = None,
    ) -> None:
        self.tool_name = tool_name
        self.method = method.upper()
        self.path_template = path_template
        self.base_url = base_url.rstrip("/")
        self.summary = summary
        self.description = description
        self.path_params = path_params or []
        self.query_params = query_params or []
        self.body_schema = body_schema

    def to_mcp_tool(self) -> Tool:
        """Convert this endpoint to an MCP Tool definition."""
        properties: dict[str, Any] = {}
        required: list[str] = []

        # Path parameters
        for p in self.path_params:
            prop = {"type": _openapi_type_to_json(p.get("schema", {}).get("type", "string"))}
            if p.get("description"):
                prop["description"] = p["description"]
            properties[p["name"]] = prop
            if p.get("required", True):
                required.append(p["name"])

        # Query parameters
        for p in self.query_params:
            prop = {"type": _openapi_type_to_json(p.get("schema", {}).get("type", "string"))}
            if p.get("description"):
                prop["description"] = p["description"]
            if "default" in p.get("schema", {}):
                prop["default"] = p["schema"]["default"]
            properties[p["name"]] = prop
            if p.get("required", False):
                required.append(p["name"])

        # Request body (flatten top-level properties)
        if self.body_schema and "properties" in self.body_schema:
            for name, schema in self.body_schema["properties"].items():
                prop = {"type": _openapi_type_to_json(schema.get("type", "string"))}
                if schema.get("description"):
                    prop["description"] = schema["description"]
                properties[name] = prop
            if "required" in self.body_schema:
                required.extend(self.body_schema["required"])

        desc = self.summary
        if self.description and self.description != self.summary:
            desc = f"{self.summary}. {self.description}" if self.summary else self.description

        input_schema = {"type": "object", "properties": properties}
        if required:
            input_schema["required"] = required

        return Tool(
            name=self.tool_name,
            description=desc or f"{self.method} {self.path_template}",
            inputSchema=input_schema,
        )

    def build_request(
        self, arguments: dict[str, Any], auth_token: str | None = None
    ) -> tuple[str, str, dict, dict, Any]:
        """
        Build an HTTP request from tool arguments.

        Returns (method, url, headers, query_params, body).
        """
        url = self.base_url + self.path_template
        headers: dict[str, str] = {"Content-Type": "application/json"}
        query: dict[str, Any] = {}
        body: dict[str, Any] | None = None

        if auth_token:
            headers["Authorization"] = f"Bearer {auth_token}"

        # Substitute path parameters
        path_param_names = {p["name"] for p in self.path_params}
        for name in path_param_names:
            if name in arguments:
                url = url.replace(f"{{{name}}}", str(arguments[name]))

        # Query parameters
        query_param_names = {p["name"] for p in self.query_params}
        for name in query_param_names:
            if name in arguments:
                query[name] = arguments[name]

        # Remaining args go to body
        if self.body_schema:
            body_props = set(self.body_schema.get("properties", {}).keys())
            body = {k: v for k, v in arguments.items() if k in body_props}

        return self.method, url, headers, query, body


class RESTVirtualizer:
    """Parses OpenAPI specs and generates MCP tools from REST endpoints."""

    def __init__(self) -> None:
        self._endpoints: dict[str, VirtualEndpoint] = {}
        self._http = httpx.AsyncClient(timeout=30.0)

    def load_spec(self, spec_path: str, base_url: str, server_name: str) -> list[Tool]:
        """Parse an OpenAPI 3.0 spec and generate MCP tool definitions."""
        path = Path(spec_path)
        if not path.exists():
            logger.error("OpenAPI spec not found: %s", spec_path)
            return []

        with open(path) as f:
            if path.suffix in (".yaml", ".yml"):
                spec = yaml.safe_load(f)
            else:
                spec = json.load(f)

        tools: list[Tool] = []
        paths = spec.get("paths", {})

        for path_str, path_item in paths.items():
            for method in ("get", "post", "put", "patch", "delete"):
                operation = path_item.get(method)
                if not operation:
                    continue

                tool_name = self._make_tool_name(operation, method, path_str, server_name)
                parameters = operation.get("parameters", []) + path_item.get("parameters", [])

                # Separate path and query params
                path_params = [p for p in parameters if p.get("in") == "path"]
                query_params = [p for p in parameters if p.get("in") == "query"]

                # Request body schema
                body_schema = None
                request_body = operation.get("requestBody")
                if request_body:
                    content = request_body.get("content", {})
                    json_content = content.get("application/json", {})
                    body_schema = self._resolve_schema(json_content.get("schema", {}), spec)

                endpoint = VirtualEndpoint(
                    tool_name=tool_name,
                    method=method,
                    path_template=path_str,
                    base_url=base_url,
                    summary=operation.get("summary", ""),
                    description=operation.get("description", ""),
                    path_params=path_params,
                    query_params=query_params,
                    body_schema=body_schema,
                )

                self._endpoints[tool_name] = endpoint
                tools.append(endpoint.to_mcp_tool())

        logger.info("Virtualized %d endpoints from %s", len(tools), spec_path)
        return tools

    def get_endpoint(self, tool_name: str) -> VirtualEndpoint | None:
        return self._endpoints.get(tool_name)

    async def call(
        self, tool_name: str, arguments: dict[str, Any], auth_token: str | None = None
    ) -> str:
        """Execute a virtualized REST call."""
        endpoint = self._endpoints.get(tool_name)
        if not endpoint:
            return json.dumps({"error": f"Unknown virtual tool: {tool_name}"})

        method, url, headers, query, body = endpoint.build_request(arguments, auth_token)

        try:
            response = await self._http.request(
                method=method,
                url=url,
                headers=headers,
                params=query if query else None,
                json=body if body else None,
            )
            return json.dumps({
                "status_code": response.status_code,
                "body": response.json() if response.headers.get("content-type", "").startswith("application/json") else response.text,
            })
        except Exception as exc:
            return json.dumps({"error": f"REST call failed: {exc}"})

    async def close(self) -> None:
        await self._http.aclose()

    @staticmethod
    def _make_tool_name(operation: dict, method: str, path: str, server_name: str) -> str:
        """Generate a tool name from the operation or method+path."""
        if "operationId" in operation:
            return operation["operationId"]
        slug = re.sub(r"[^a-zA-Z0-9]", "_", path.strip("/"))
        slug = re.sub(r"_+", "_", slug).strip("_")
        return f"{method}_{slug}"

    @staticmethod
    def _resolve_schema(schema: dict, spec: dict) -> dict:
        """Resolve $ref pointers in schemas (one level)."""
        if "$ref" in schema:
            ref_path = schema["$ref"].lstrip("#/").split("/")
            resolved = spec
            for part in ref_path:
                resolved = resolved.get(part, {})
            return resolved
        return schema


def _openapi_type_to_json(openapi_type: str) -> str:
    """Map OpenAPI types to JSON Schema types."""
    mapping = {
        "integer": "integer",
        "number": "number",
        "string": "string",
        "boolean": "boolean",
        "array": "array",
        "object": "object",
    }
    return mapping.get(openapi_type, "string")
