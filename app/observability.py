import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": _ts(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        extra_fields = getattr(record, "fields", None)
        if isinstance(extra_fields, dict):
            payload.update(extra_fields)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


class StructuredLogger:
    def __init__(self, name: str):
        self._logger = logging.getLogger(name)

    def info(self, message: str, **fields: Any) -> None:
        self._logger.info(message, extra={"fields": fields})

    def warning(self, message: str, **fields: Any) -> None:
        self._logger.warning(message, extra={"fields": fields})

    def error(self, message: str, **fields: Any) -> None:
        self._logger.error(message, extra={"fields": fields})

    def exception(self, message: str, **fields: Any) -> None:
        self._logger.exception(message, extra={"fields": fields})


def configure_logging() -> None:
    level = os.getenv("LOG_LEVEL", "INFO").upper()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(level)
    root.addHandler(handler)
