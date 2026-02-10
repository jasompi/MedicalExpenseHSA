"""Logging configuration using structlog."""

import sys
import structlog
from pathlib import Path


def setup_logger(log_level: str = "INFO", log_file: str | None = None) -> None:
    """Setup structured logging with console and optional file output.

    Args:
        log_level: Log level (DEBUG, INFO, WARNING, ERROR)
        log_file: Optional path to log file
    """
    # Configure structlog processors
    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.dev.set_exc_info,
        structlog.processors.TimeStamper(fmt="iso"),
    ]

    # Add console renderer
    if sys.stderr.isatty():
        # Pretty console output for interactive terminals
        processors.append(structlog.dev.ConsoleRenderer())
    else:
        # JSON output for non-interactive (e.g., logs)
        processors.append(structlog.processors.JSONRenderer())

    # Configure structlog
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            _get_log_level(log_level)
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # If log file specified, also write to file
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)


def _get_log_level(level_name: str) -> int:
    """Get numeric log level from string name.

    Args:
        level_name: Log level name (DEBUG, INFO, WARNING, ERROR)

    Returns:
        Numeric log level
    """
    import logging
    return getattr(logging, level_name.upper(), logging.INFO)


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Get a logger instance.

    Args:
        name: Logger name (typically __name__)

    Returns:
        Configured logger instance
    """
    return structlog.get_logger(name)
