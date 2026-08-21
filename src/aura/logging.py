"""AURA logging — structured, contextual, production-ready.

All logs go to stderr. Stdout is reserved for clean CLI/data output.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog


def configure_logging(
    level: str = "WARNING",
    json_output: bool = False,
    job_id: str = "",
) -> None:
    """Configure structured logging. All logs → stderr."""
    timestamper = structlog.processors.TimeStamper(fmt="iso")

    if json_output:
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty())

    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            timestamper,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            renderer,
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Force root logger to stderr — clear any existing handlers first
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(getattr(logging, level.upper(), logging.WARNING))

    handler = logging.StreamHandler(sys.stderr)
    handler.setLevel(getattr(logging, level.upper(), logging.WARNING))
    handler.setFormatter(logging.Formatter("%(message)s"))
    root.addHandler(handler)

    # Silence noisy third-party loggers
    for noisy in ("urllib3", "httpx", "asyncio", "sqlite3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str = "aura", **context: Any) -> structlog.stdlib.BoundLogger:
    """Get a structured logger with optional context."""
    logger = structlog.get_logger(name)
    if context:
        logger = logger.bind(**context)
    return logger


log = get_logger()