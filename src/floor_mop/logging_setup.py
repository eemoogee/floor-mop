"""Application logging setup for Floor Mop."""

from __future__ import annotations

import json
import logging
import logging.handlers
import sys
import time
from datetime import UTC, datetime
from typing import Any, Final

from floor_mop.config import Settings

LOGGER_NAME: Final[str] = "floor_mop"
LOG_FILENAME: Final[str] = "floor_mop.log"

_MARK_ATTR: Final[str] = "_floor_mop_managed"

_STANDARD_ATTRS: Final[frozenset[str]] = frozenset(
    logging.LogRecord(
        "", 0, "", 0, "", (), None
    ).__dict__.keys()
) | {"message", "asctime"}


class JsonLineFormatter(logging.Formatter):
    """Formats each log record as a single line of JSON."""

    def format(self, record: logging.LogRecord) -> str:
        """Render a log record as one JSON line."""
        timestamp = datetime.fromtimestamp(record.created, tz=UTC)
        payload: dict[str, Any] = {
            "ts": timestamp.strftime("%Y-%m-%dT%H:%M:%S.") + f"{timestamp.microsecond // 1000:03d}Z",
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }

        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)

        extra = {
            key: value
            for key, value in record.__dict__.items()
            if key not in _STANDARD_ATTRS
        }
        if extra:
            payload["extra"] = extra

        return json.dumps(payload, default=str, ensure_ascii=False)


def _clear_managed_handlers(logger: logging.Logger) -> None:
    """Remove and close every handler this module previously installed."""
    for handler in list(logger.handlers):
        if getattr(handler, _MARK_ATTR, False):
            logger.removeHandler(handler)
            handler.close()


def setup_logging(settings: Settings) -> logging.Logger:
    """Configure the Floor Mop application logger from settings."""
    logger = logging.getLogger(LOGGER_NAME)
    _clear_managed_handlers(logger)

    logger.setLevel(settings.logging.level)

    settings.logging.dir.mkdir(parents=True, exist_ok=True)
    log_path = settings.logging.dir / LOG_FILENAME

    file_handler = logging.handlers.RotatingFileHandler(
        log_path,
        maxBytes=settings.logging.max_bytes,
        backupCount=settings.logging.backup_count,
        encoding="utf-8",
    )
    file_handler.setFormatter(JsonLineFormatter())
    setattr(file_handler, _MARK_ATTR, True)
    logger.addHandler(file_handler)

    if settings.logging.console:
        console_handler = logging.StreamHandler(sys.stderr)
        console_formatter = logging.Formatter(
            "%(asctime)s %(levelname)-8s %(name)s: %(message)s"
        )
        console_formatter.converter = time.gmtime
        console_handler.setFormatter(console_formatter)
        setattr(console_handler, _MARK_ATTR, True)
        logger.addHandler(console_handler)

    return logger


def teardown_logging() -> None:
    """Remove and close every handler installed by setup_logging."""
    logger = logging.getLogger(LOGGER_NAME)
    _clear_managed_handlers(logger)
