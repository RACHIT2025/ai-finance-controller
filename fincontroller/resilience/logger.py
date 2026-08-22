"""
Structured JSON Logger and Real-Time Telemetry Event Buffer.
Ensures every fallback and resilience event is visibly recorded.
"""

from collections import deque
from datetime import datetime
import json
import logging
import sys
from typing import Any, Dict, List, Optional


class TelemetryBuffer:
    """In-memory circular buffer for dashboard and CLI event streaming."""
    _instance = None
    _events: deque = deque(maxlen=200)

    @classmethod
    def get_instance(cls) -> "TelemetryBuffer":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def push(self, level: str, component: str, message: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        from datetime import timezone
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": level.upper(),
            "component": component,
            "message": message,
            "metadata": metadata or {},
        }
        self._events.appendleft(event)
        return event

    def get_recent(self, limit: int = 50) -> List[Dict[str, Any]]:
        return list(self._events)[:limit]

    def clear(self) -> None:
        self._events.clear()


telemetry = TelemetryBuffer.get_instance()


class JSONFormatter(logging.Formatter):
    """Formats log records as structured JSON."""
    def format(self, record: logging.LogRecord) -> str:
        from datetime import timezone
        log_obj = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if hasattr(record, "metadata") and record.metadata:
            log_obj["metadata"] = record.metadata
        return json.dumps(log_obj)


def get_logger(name: str = "fincontroller") -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JSONFormatter())
        logger.addHandler(handler)
    return logger
