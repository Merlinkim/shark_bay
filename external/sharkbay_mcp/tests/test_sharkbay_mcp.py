from __future__ import annotations

import json


from openapi_client import OpenAPIClient, SimpleResponse
from python_version import build_version_error, enforce_supported_python
from safety import redact
from schema_registry import SchemaRegistry

MOCK_OPENAPI = {
    "openapi": "3.1.0",
    "info": {"title": "Mock SharkBay", "version": "test"},
    "paths": {
        "/health": {
            "get": {
                "operationId": "health_get",
                "summary": "Health",
                "tags": ["system"],
                "responses": {"200": {"content": {"application/json": {"schema": {"type": "object"}}}}},
            }
        },
        "/items/{item_id}": {
            "get": {
                "operationId": "items_read",
                "summary": "Read item",
                "tags": ["items"],
                "parameters": [
                    {"name": "item_id", "in": "path", "required": True, "schema": {"type": "string"}},
                    {"name": "verbose", "in": "query", "required": False, "schema": {"type": "boolean"}},
                ],
                "responses": {"200": {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/Item"}}}}},
            }
        },
        "/orders": {
            "post": {
                "operationId": "orders_create",
                "summary": "Create order",
                "tags": ["orders"],
                "requestBody": {
                    "required": True,
                    "content": {"application/json": {"schema": {"type": "object", "required": ["symbol"]}}},
                },
                "responses": {"201": {"content": {"application/json": {"schema": {"type": "object"}}}}},
            }
        },
    },
}


class FakeTransport:
    def __init__(self, handler):
        self.handler = handler

    def get(self, url, *, headers=None, timeout=10):
        return self.handler("GET", url, headers=headers or {}, params=None, json_body=None)

    def request(self, method, url, *, params=None, json_body=None, headers=None, timeout=10):
        return self.handler(method, url, headers=headers or {}, params=params, json_body=json_body)


def make_client(handler, *, max_response_bytes: int = 1_048_576) -> OpenAPIClient:
    return OpenAPIClient(
        base_url="https://api.example.test",
        api_key="Bearer super-secret-token",
        max_response_bytes=max_response_bytes,
        http_client=FakeTransport(handler),
    )


def test_list_endpoints() -> None:
    registry = SchemaRegistry(MOCK_OPENAPI)

    endpoints = registry.list_endpoints()

    assert {endpoint["endpoint_id"] for endpoint in endpoints} == {"health_get", "items_read", "orders_create"}
    item_endpoint = next(endpoint for endpoint in endpoints if endpoint["endpoint_id"] == "items_read")
    assert item_endpoint["method"] == "GET"
    assert item_endpoint["path"] == "/items/{item_id}"
    assert item_endpoint["required_parameters"] == ["path.item_id"]


def test_get_endpoint_schema() -> None:
    registry = SchemaRegistry(MOCK_OPENAPI)

    schema = registry.get_endpoint_schema("orders_create")

    assert schema["method"] == "POST"
    assert schema["path"] == "/orders"
    assert schema["request_body_schema"]["required"] == ["symbol"]
    assert schema["required_fields"] == ["body"]


def test_call_endpoint_success() -> None:
    def handler(method, url, *, headers, params, json_body):
        if url.endswith("/openapi.json"):
            return SimpleResponse(200, json.dumps(MOCK_OPENAPI).encode(), {"content-type": "application/json"})
        assert url == "https://api.example.test/items/BTCUSDT"
        assert headers["Authorization"] == "Bearer super-secret-token"
        return SimpleResponse(200, json.dumps({"item_id": "BTCUSDT", "token": "must-not-leak"}).encode(), {"x-request-id": "req-1", "content-type": "application/json"})

    client = make_client(handler)

    result = client.call_endpoint("items_read", path_params={"item_id": "BTCUSDT"}, query_params={"verbose": True})

    assert result["success"] is True
    assert result["status_code"] == 200
    assert result["request_id"] == "req-1"
    assert result["response_summary"] == {"item_id": "BTCUSDT", "token": "[REDACTED]"}


def test_call_endpoint_missing_required_parameter() -> None:
    client = make_client(lambda method, url, **kwargs: SimpleResponse(200, json.dumps(MOCK_OPENAPI).encode(), {"content-type": "application/json"}))

    result = client.call_endpoint("items_read")

    assert result["success"] is False
    assert "Missing required parameter" in result["error_summary"]
    assert "path.item_id" in result["error_summary"]


def test_call_endpoint_endpoint_not_found() -> None:
    client = make_client(lambda method, url, **kwargs: SimpleResponse(200, json.dumps(MOCK_OPENAPI).encode(), {"content-type": "application/json"}))

    result = client.call_endpoint("does_not_exist")

    assert result["success"] is False
    assert result["status_code"] is None
    assert "Endpoint not found" in result["error_summary"]


def test_secret_redaction() -> None:
    payload = {
        "Authorization": "Bearer abc123",
        "nested": {"api_key": "xyz", "message": "token=abc123 cookie=sessionid"},
    }

    assert redact(payload) == {
        "Authorization": "[REDACTED]",
        "nested": {"api_key": "[REDACTED]", "message": "token=[REDACTED] cookie=[REDACTED]"},
    }


def test_response_truncation() -> None:
    large_body = {"data": "x" * 100}

    def handler(method, url, *, headers, params, json_body):
        if url.endswith("/openapi.json"):
            return SimpleResponse(200, json.dumps(MOCK_OPENAPI).encode(), {"content-type": "application/json"})
        return SimpleResponse(200, json.dumps(large_body).encode(), {"content-type": "application/json"})

    client = make_client(handler, max_response_bytes=20)

    result = client.call_endpoint("health_get")

    assert result["success"] is True
    assert result["truncated"] is True
    assert isinstance(result["response_summary"], str)


def test_python_version_error_message_for_unsupported_runtime(capsys) -> None:
    try:
        enforce_supported_python((3, 9, 6))
    except SystemExit as exc:
        assert exc.code == 1
    else:
        raise AssertionError("Expected SystemExit for Python 3.9")

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == build_version_error((3, 9, 6)) + "\n"
    assert "Python 3.10+ is required" in captured.err
    assert "Python 3.9.6" in captured.err
    assert "Python 3.12" in captured.err


def test_python_version_check_allows_supported_runtime() -> None:
    enforce_supported_python((3, 10, 0))
    enforce_supported_python((3, 12, 1))
