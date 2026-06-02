"""Standalone MCP server for calling SharkBay through its public REST API."""

from __future__ import annotations

from typing import Any

from python_version import enforce_supported_python

enforce_supported_python()

from mcp.server.fastmcp import FastMCP

from openapi_client import OpenAPIClient
from safety import safe_error_summary

mcp = FastMCP("sharkbay")
_client: OpenAPIClient | None = None


def get_client() -> OpenAPIClient:
    global _client
    if _client is None:
        _client = OpenAPIClient.from_env()
    return _client


@mcp.tool()
def health_check() -> dict[str, Any]:
    """Check whether the remote SharkBay API is reachable."""
    return get_client().health_check()


@mcp.tool()
def list_endpoints() -> dict[str, Any]:
    """Read OpenAPI and return available SharkBay endpoints."""
    try:
        return {"success": True, "endpoints": get_client().registry().list_endpoints()}
    except Exception as exc:
        return {"success": False, "error_summary": safe_error_summary(exc), "endpoints": []}


@mcp.tool()
def get_endpoint_schema(endpoint_id: str) -> dict[str, Any]:
    """Return OpenAPI schema details for a single endpoint ID."""
    try:
        return {"success": True, "schema": get_client().registry().get_endpoint_schema(endpoint_id)}
    except KeyError as exc:
        return {"success": False, "error_summary": safe_error_summary(exc), "schema": None}


@mcp.tool()
def call_endpoint(
    endpoint_id: str,
    path_params: dict[str, Any] | None = None,
    query_params: dict[str, Any] | None = None,
    json_body: Any = None,
    return_raw: bool = False,
) -> dict[str, Any]:
    """Call a SharkBay endpoint listed in OpenAPI using SHARKBAY_BASE_URL only."""
    return get_client().call_endpoint(
        endpoint_id=endpoint_id,
        path_params=path_params or {},
        query_params=query_params or {},
        json_body=json_body,
        return_raw=return_raw,
    )


if __name__ == "__main__":
    mcp.run()
