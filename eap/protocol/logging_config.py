import json
import logging
import os
import re
import sys
from typing import Optional, TextIO


class JsonFormatter(logging.Formatter):
    """Simple JSON formatter for production-friendly logs."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp_utc": self.formatTime(record, datefmt="%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if hasattr(record, "step_id"):
            payload["step_id"] = record.step_id
        if hasattr(record, "tool_name"):
            payload["tool_name"] = record.tool_name
        return json.dumps(payload, ensure_ascii=True)


class RedactionFilter(logging.Filter):
    """Redacts common secret patterns from log messages."""

    _pattern = re.compile(r"(?i)(api[_-]?key|token|password)\s*[:=]\s*([^\s,;]+)")

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        redacted = self._pattern.sub(lambda m: f"{m.group(1)}=[REDACTED]", message)
        if redacted != message:
            record.msg = redacted
            record.args = ()
        return True


def configure_logging(
    level: Optional[str] = None,
    use_json: Optional[bool] = None,
    log_format: Optional[str] = None,
    stream: Optional[TextIO] = None,
) -> logging.Logger:
    """
    Configure EAP logging once and return the base logger.

    Environment variables:
    - EAP_LOG_LEVEL: DEBUG/INFO/WARNING/ERROR (default INFO)
    - EAP_LOG_FORMAT: json|text (default json)
    - EAP_LOG_JSON: legacy bool override for JSON output
    """
    logger = logging.getLogger("eap")
    logger.handlers.clear()

    level_name = (level or os.getenv("EAP_LOG_LEVEL", "INFO")).upper()
    log_level = getattr(logging, level_name, logging.INFO)
    logger.setLevel(log_level)

    json_enabled = use_json
    if json_enabled is None:
        requested_format = (log_format or os.getenv("EAP_LOG_FORMAT", "json")).strip().lower()
        if requested_format not in {"json", "text"}:
            requested_format = "json"
        json_enabled = requested_format == "json"

        legacy_json_flag = os.getenv("EAP_LOG_JSON", "").strip()
        if legacy_json_flag:
            json_enabled = legacy_json_flag.lower() in {"1", "true", "yes"}

    handler = logging.StreamHandler(stream or sys.stdout)
    handler.addFilter(RedactionFilter())
    if json_enabled:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s"))

    logger.addHandler(handler)
    logger.propagate = False
    return logger
