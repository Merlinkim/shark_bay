"""HTTP/OpenAPI client used by the standalone SharkBay MCP server."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from safety import parse_json_or_text, redact, safe_error_summary, summarize_json, truncate_bytes
from schema_registry import SchemaRegistry

DEFAULT_TIMEOUT_SECONDS = 10.0
DEFAULT_MAX_RESPONSE_BYTES = 1_048_576
DEFAULT_LOCAL_OPENAPI_FILE = "openapi.json"


class HTTPError(Exception):
    """Raised for transport-level HTTP client failures."""


class SimpleResponse:
    """Small response wrapper used by the stdlib transport and tests."""

    def __init__(self, status_code: int, content: bytes = b"", headers: dict[str, str] | None = None) -> None:
        self.status_code = status_code
        self.content = content
        self.headers = {key.lower(): value for key, value in (headers or {}).items()}

    def json(self) -> Any:
        return json.loads(self.content.decode("utf-8"))

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise HTTPError(f"HTTP {self.status_code}")


class URLRequestTransport:
    """Minimal urllib-based transport so the MCP runtime has one fewer hard dependency."""

    def request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: Any = None,
        headers: dict[str, str] | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> SimpleResponse:
        if params:
            query = urllib.parse.urlencode(params, doseq=True)
            separator = "&" if urllib.parse.urlparse(url).query else "?"
            url = f"{url}{separator}{query}"
        data = None
        request_headers = dict(headers or {})
        if json_body is not None:
            data = json.dumps(json_body).encode("utf-8")
            request_headers.setdefault("Content-Type", "application/json")
        request = urllib.request.Request(url, data=data, headers=request_headers, method=method.upper())
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                content = response.read()
                return SimpleResponse(response.status, content, dict(response.headers.items()))
        except urllib.error.HTTPError as exc:
            return SimpleResponse(exc.code, exc.read(), dict(exc.headers.items()))
        except urllib.error.URLError as exc:
            raise HTTPError(str(exc)) from exc

    def get(self, url: str, *, headers: dict[str, str] | None = None, timeout: float = DEFAULT_TIMEOUT_SECONDS) -> SimpleResponse:
        return self.request("GET", url, headers=headers, timeout=timeout)


class OpenAPIClient:
    """Remote-only SharkBay REST client driven by OpenAPI."""

    def __init__(
        self,
        base_url: str,
        openapi_url: str | None = None,
        api_key: str | None = None,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
        local_openapi_file: str | Path = DEFAULT_LOCAL_OPENAPI_FILE,
        http_client: Any | None = None,
    ) -> None:
        if not base_url:
            raise ValueError("SHARKBAY_BASE_URL is required")
        parsed = urllib.parse.urlparse(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("SHARKBAY_BASE_URL must be an http(s) URL")
        self.base_url = base_url.rstrip("/") + "/"
        self.openapi_url = openapi_url or urllib.parse.urljoin(self.base_url, "openapi.json")
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.max_response_bytes = max_response_bytes
        self.local_openapi_file = Path(local_openapi_file)
        self.http_client = http_client or URLRequestTransport()
        self._registry: SchemaRegistry | None = None

    @classmethod
    def from_env(cls) -> "OpenAPIClient":
        module_dir = Path(__file__).resolve().parent
        local_file = os.environ.get("SHARKBAY_LOCAL_OPENAPI_FILE", DEFAULT_LOCAL_OPENAPI_FILE)
        local_path = Path(local_file)
        if not local_path.is_absolute():
            local_path = module_dir / local_path
        return cls(
            base_url=os.environ.get("SHARKBAY_BASE_URL", ""),
            openapi_url=os.environ.get("SHARKBAY_OPENAPI_URL") or None,
            api_key=os.environ.get("SHARKBAY_API_KEY") or None,
            timeout_seconds=float(os.environ.get("SHARKBAY_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS)),
            max_response_bytes=int(os.environ.get("SHARKBAY_MAX_RESPONSE_BYTES", DEFAULT_MAX_RESPONSE_BYTES)),
            local_openapi_file=local_path,
        )

    def health_check(self) -> dict[str, Any]:
        try:
            response = self.http_client.get(urllib.parse.urljoin(self.base_url, "openapi.json"), headers=self._headers(), timeout=self.timeout_seconds)
            return {
                "success": response.status_code < 500,
                "status_code": response.status_code,
                "base_url": self.base_url.rstrip("/"),
                "openapi_url": self.openapi_url,
                "request_id": self._request_id(response),
            }
        except Exception as exc:
            return {
                "success": False,
                "status_code": None,
                "base_url": self.base_url.rstrip("/"),
                "openapi_url": self.openapi_url,
                "error_summary": safe_error_summary(exc),
            }

    def registry(self) -> SchemaRegistry:
        if self._registry is None:
            self._registry = SchemaRegistry(self.load_openapi_schema())
        return self._registry

    def load_openapi_schema(self) -> dict[str, Any]:
        try:
            response = self.http_client.get(self.openapi_url, headers=self._headers(), timeout=self.timeout_seconds)
            response.raise_for_status()
            return response.json()
        except Exception:
            if self.local_openapi_file.exists():
                return json.loads(self.local_openapi_file.read_text(encoding="utf-8"))
            raise

    def call_endpoint(
        self,
        endpoint_id: str,
        path_params: dict[str, Any] | None = None,
        query_params: dict[str, Any] | None = None,
        json_body: Any = None,
        return_raw: bool = False,
    ) -> dict[str, Any]:
        path_params = path_params or {}
        query_params = query_params or {}
        registry = self.registry()
        endpoint = registry.resolve(endpoint_id)
        if endpoint is None:
            return {
                "status_code": None,
                "success": False,
                "response_summary": None,
                "error_summary": f"Endpoint not found: {redact(endpoint_id)}",
                "request_id": None,
                "truncated": False,
            }
        try:
            registry.validate_required(endpoint, path_params, json_body=json_body)
            rendered_path = registry.render_path(endpoint, path_params)
            url = self._endpoint_url(rendered_path)
            response = self.http_client.request(
                endpoint.method,
                url,
                params=query_params,
                json_body=json_body,
                headers=self._headers(),
                timeout=self.timeout_seconds,
            )
            limited_content, truncated = truncate_bytes(response.content, self.max_response_bytes)
            parsed = parse_json_or_text(limited_content, response.headers.get("content-type"))
            raw_or_summary = redact(parsed) if return_raw else summarize_json(parsed)
            return {
                "status_code": response.status_code,
                "success": 200 <= response.status_code < 400,
                "response_summary": raw_or_summary if 200 <= response.status_code < 400 else None,
                "error_summary": None if 200 <= response.status_code < 400 else raw_or_summary,
                "request_id": self._request_id(response),
                "truncated": truncated,
            }
        except (ValueError, HTTPError) as exc:
            return {
                "status_code": None,
                "success": False,
                "response_summary": None,
                "error_summary": safe_error_summary(exc),
                "request_id": None,
                "truncated": False,
            }

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = self.api_key
        return headers

    def _endpoint_url(self, rendered_path: str) -> str:
        relative = rendered_path.lstrip("/")
        url = urllib.parse.urljoin(self.base_url, relative)
        base = urllib.parse.urlparse(self.base_url)
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme != base.scheme or parsed.netloc != base.netloc:
            raise ValueError("Resolved endpoint URL escaped SHARKBAY_BASE_URL")
        return url

    def _request_id(self, response: SimpleResponse) -> str | None:
        for header in ("x-request-id", "x-correlation-id", "request-id"):
            value = response.headers.get(header)
            if value:
                return value
        return None
