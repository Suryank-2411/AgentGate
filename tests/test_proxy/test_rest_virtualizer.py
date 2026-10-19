"""Tests for the REST-to-MCP virtualization layer."""

import json
from pathlib import Path

import pytest

from agentgateway.proxy.rest_virtualizer import RESTVirtualizer


@pytest.fixture
def spec_path() -> str:
    return str(Path(__file__).parent.parent.parent / "config" / "sample_api.yaml")


@pytest.fixture
def virtualizer(spec_path: str) -> RESTVirtualizer:
    v = RESTVirtualizer()
    v.load_spec(spec_path, base_url="http://localhost:9003", server_name="pet-store")
    return v


class TestRESTVirtualizer:
    def test_load_spec_generates_tools(self, virtualizer: RESTVirtualizer):
        tools = list(virtualizer._endpoints.keys())
        assert "list_pets" in tools
        assert "create_pet" in tools
        assert "get_pet" in tools
        assert "delete_pet" in tools
        assert len(tools) == 4

    def test_list_pets_tool_schema(self, virtualizer: RESTVirtualizer):
        endpoint = virtualizer.get_endpoint("list_pets")
        tool = endpoint.to_mcp_tool()
        assert tool.name == "list_pets"
        assert "list" in tool.description.lower() or "pets" in tool.description.lower()
        props = tool.input_schema["properties"]
        assert "species" in props
        assert "limit" in props
        assert props["limit"]["type"] == "integer"

    def test_create_pet_tool_schema(self, virtualizer: RESTVirtualizer):
        endpoint = virtualizer.get_endpoint("create_pet")
        tool = endpoint.to_mcp_tool()
        props = tool.input_schema["properties"]
        assert "name" in props
        assert "species" in props
        assert "age" in props
        assert "name" in tool.input_schema.get("required", [])

    def test_get_pet_tool_has_path_param(self, virtualizer: RESTVirtualizer):
        endpoint = virtualizer.get_endpoint("get_pet")
        tool = endpoint.to_mcp_tool()
        props = tool.input_schema["properties"]
        assert "pet_id" in props
        assert props["pet_id"]["type"] == "integer"

    def test_build_get_request(self, virtualizer: RESTVirtualizer):
        endpoint = virtualizer.get_endpoint("get_pet")
        method, url, headers, query, body = endpoint.build_request({"pet_id": 42})
        assert method == "GET"
        assert "42" in url
        assert "{pet_id}" not in url

    def test_build_post_request(self, virtualizer: RESTVirtualizer):
        endpoint = virtualizer.get_endpoint("create_pet")
        method, url, headers, query, body = endpoint.build_request(
            {"name": "Max", "species": "dog", "age": 3}
        )
        assert method == "POST"
        assert body == {"name": "Max", "species": "dog", "age": 3}

    def test_build_request_with_query_params(self, virtualizer: RESTVirtualizer):
        endpoint = virtualizer.get_endpoint("list_pets")
        method, url, headers, query, body = endpoint.build_request(
            {"species": "cat", "limit": 5}
        )
        assert method == "GET"
        assert query == {"species": "cat", "limit": 5}

    def test_build_request_with_auth(self, virtualizer: RESTVirtualizer):
        endpoint = virtualizer.get_endpoint("list_pets")
        _, _, headers, _, _ = endpoint.build_request({}, auth_token="my-token")
        assert headers["Authorization"] == "Bearer my-token"

    def test_missing_spec_returns_empty(self):
        v = RESTVirtualizer()
        tools = v.load_spec("/nonexistent.yaml", base_url="http://x", server_name="x")
        assert tools == []

    def test_unknown_endpoint_returns_none(self, virtualizer: RESTVirtualizer):
        assert virtualizer.get_endpoint("nonexistent") is None
