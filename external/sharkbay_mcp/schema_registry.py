"""OpenAPI schema indexing for the standalone SharkBay MCP server."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any

HTTP_METHODS = {"get", "post", "put", "patch", "delete", "head", "options"}


@dataclass(frozen=True)
class Endpoint:
    endpoint_id: str
    method: str
    path: str
    operation: dict[str, Any]


class SchemaRegistry:
    """Indexes OpenAPI operations without importing the SharkBay application."""

    def __init__(self, schema: dict[str, Any]) -> None:
        self.schema = schema
        self._endpoints = self._build_index(schema)

    def list_endpoints(self) -> list[dict[str, Any]]:
        return [self._endpoint_summary(endpoint) for endpoint in self._endpoints.values()]

    def get_endpoint_schema(self, endpoint_id: str) -> dict[str, Any]:
        endpoint = self.resolve(endpoint_id)
        if endpoint is None:
            raise KeyError(f"Endpoint not found: {endpoint_id}")
        parameters = endpoint.operation.get("parameters", [])
        path_params = [p for p in parameters if p.get("in") == "path"]
        query_params = [p for p in parameters if p.get("in") == "query"]
        return {
            "endpoint_id": endpoint.endpoint_id,
            "method": endpoint.method,
            "path": endpoint.path,
            "summary": endpoint.operation.get("summary", ""),
            "tags": endpoint.operation.get("tags", []),
            "path_parameters": path_params,
            "query_parameters": query_params,
            "request_body_schema": self._request_body_schema(endpoint.operation),
            "response_schema": self._response_schema(endpoint.operation),
            "required_fields": self.required_parameters(endpoint),
        }

    def resolve(self, endpoint_id: str) -> Endpoint | None:
        return self._endpoints.get(endpoint_id)

    def required_parameters(self, endpoint: Endpoint) -> list[str]:
        required = []
        for param in endpoint.operation.get("parameters", []):
            if param.get("required"):
                location = param.get("in", "parameter")
                required.append(f"{location}.{param.get('name')}")
        body = endpoint.operation.get("requestBody")
        if body and body.get("required"):
            required.append("body")
        return required

    def validate_required(self, endpoint: Endpoint, path_params: dict[str, Any], json_body: Any = None) -> None:
        missing = []
        for param in endpoint.operation.get("parameters", []):
            if param.get("required") and param.get("in") == "path" and param.get("name") not in path_params:
                missing.append(f"path.{param.get('name')}")
        if endpoint.operation.get("requestBody", {}).get("required") and json_body is None:
            missing.append("body")
        if missing:
            raise ValueError(f"Missing required parameter(s): {', '.join(missing)}")

    def render_path(self, endpoint: Endpoint, path_params: dict[str, Any]) -> str:
        self.validate_required(endpoint, path_params)

        def replace(match: re.Match[str]) -> str:
            name = match.group(1)
            if name not in path_params:
                raise ValueError(f"Missing required parameter(s): path.{name}")
            return str(path_params[name]).strip("/")

        return re.sub(r"\{([^}]+)\}", replace, endpoint.path)

    def _build_index(self, schema: dict[str, Any]) -> dict[str, Endpoint]:
        endpoints: dict[str, Endpoint] = {}
        for path, path_item in schema.get("paths", {}).items():
            if not isinstance(path_item, dict):
                continue
            common_params = path_item.get("parameters", [])
            for method, operation in path_item.items():
                method_lower = method.lower()
                if method_lower not in HTTP_METHODS or not isinstance(operation, dict):
                    continue
                op = dict(operation)
                if common_params:
                    op["parameters"] = [*common_params, *op.get("parameters", [])]
                endpoint_id = self._endpoint_id(method_lower, path, op)
                endpoints[endpoint_id] = Endpoint(endpoint_id, method_lower.upper(), path, op)
        return dict(sorted(endpoints.items()))

    def _endpoint_id(self, method: str, path: str, operation: dict[str, Any]) -> str:
        operation_id = operation.get("operationId")
        if operation_id:
            return str(operation_id)
        slug = re.sub(r"[^a-zA-Z0-9]+", "_", f"{method}_{path}").strip("_").lower()
        digest = hashlib.sha1(f"{method}:{path}".encode()).hexdigest()[:8]
        return f"{slug}_{digest}"

    def _endpoint_summary(self, endpoint: Endpoint) -> dict[str, Any]:
        return {
            "endpoint_id": endpoint.endpoint_id,
            "method": endpoint.method,
            "path": endpoint.path,
            "summary": endpoint.operation.get("summary", ""),
            "tags": endpoint.operation.get("tags", []),
            "required_parameters": self.required_parameters(endpoint),
        }

    def _request_body_schema(self, operation: dict[str, Any]) -> dict[str, Any] | None:
        body = operation.get("requestBody")
        if not body:
            return None
        content = body.get("content", {})
        return content.get("application/json", {}).get("schema") or body

    def _response_schema(self, operation: dict[str, Any]) -> dict[str, Any] | None:
        responses = operation.get("responses", {})
        for status in ("200", "201", "202", "204", "default"):
            response = responses.get(status)
            if not response:
                continue
            content = response.get("content", {})
            return content.get("application/json", {}).get("schema") or response
        return None
