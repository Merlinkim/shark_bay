"""Safety helpers for the standalone SharkBay MCP server."""

from __future__ import annotations

import json
import re
from typing import Any

SECRET_FIELD_PATTERN = re.compile(
    r"(authorization|api[-_]?key|access[-_]?token|refresh[-_]?token|token|secret|password|cookie|set-cookie)",
    re.IGNORECASE,
)
BEARER_PATTERN = re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]+", re.IGNORECASE)
KEY_VALUE_SECRET_PATTERN = re.compile(
    r"(?i)(authorization|api[-_]?key|access[-_]?token|refresh[-_]?token|token|secret|password|cookie)([\s:=]+)([^\s,;\]}]+)"
)
REDACTED = "[REDACTED]"


def redact(value: Any) -> Any:
    """Return a copy of value with common secret fields and tokens redacted."""
    if isinstance(value, dict):
        redacted: dict[Any, Any] = {}
        for key, item in value.items():
            if SECRET_FIELD_PATTERN.search(str(key)):
                redacted[key] = REDACTED
            else:
                redacted[key] = redact(item)
        return redacted
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact(item) for item in value)
    if isinstance(value, str):
        text = BEARER_PATTERN.sub(f"Bearer {REDACTED}", value)
        return KEY_VALUE_SECRET_PATTERN.sub(lambda m: f"{m.group(1)}{m.group(2)}{REDACTED}", text)
    return value


def safe_error_summary(exc: BaseException | str) -> str:
    """Build a short, redacted error string safe to return to OpenClaw."""
    text = str(exc)
    redacted = redact(text)
    return redacted[:1000]


def truncate_bytes(content: bytes, max_bytes: int) -> tuple[bytes, bool]:
    """Truncate bytes to max_bytes and report whether truncation occurred."""
    if max_bytes < 1:
        max_bytes = 1
    if len(content) <= max_bytes:
        return content, False
    return content[:max_bytes], True


def summarize_json(value: Any, max_items: int = 20) -> Any:
    """Create a bounded JSON-compatible summary without persisting response data."""
    value = redact(value)
    if isinstance(value, dict):
        items = list(value.items())[:max_items]
        summary = {key: summarize_json(item, max_items=max_items) for key, item in items}
        if len(value) > max_items:
            summary["__truncated_keys__"] = len(value) - max_items
        return summary
    if isinstance(value, list):
        items = [summarize_json(item, max_items=max_items) for item in value[:max_items]]
        if len(value) > max_items:
            items.append({"__truncated_items__": len(value) - max_items})
        return items
    if isinstance(value, str) and len(value) > 2000:
        return value[:2000] + "... [truncated]"
    return value


def parse_json_or_text(content: bytes, content_type: str | None = None) -> Any:
    """Parse response bytes as JSON when possible, otherwise return decoded text."""
    text = content.decode("utf-8", errors="replace")
    if content_type and "json" not in content_type.lower():
        return text
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text
