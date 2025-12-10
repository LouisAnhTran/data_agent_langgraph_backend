"""Logging configuration for Data Agent LangGraph"""

import logging
import sys
from pathlib import Path
from logging.handlers import RotatingFileHandler
from typing import Optional


def setup_logging(
    log_level: str = "INFO",
    log_to_file: bool = True,
    log_file: Optional[str] = None,
    log_dir: str = "logs",
) -> None:
    """
    Configure application-wide logging settings

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_to_file: Whether to log to file in addition to console
        log_file: Custom log file name (defaults to 'app.log')
        log_dir: Directory for log files (defaults to 'logs')
    """
    # Create logs directory if it doesn't exist
    if log_to_file:
        log_path = Path(log_dir)
        log_path.mkdir(exist_ok=True)

        if log_file is None:
            log_file = log_path / "app.log"
        else:
            log_file = log_path / log_file

    # Define log format
    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"

    # Create formatter
    formatter = logging.Formatter(log_format, datefmt=date_format)

    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper()))

    # Remove existing handlers
    root_logger.handlers.clear()

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, log_level.upper()))
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # File handler (with rotation)
    if log_to_file:
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5,
            encoding="utf-8"
        )
        file_handler.setLevel(getattr(logging, log_level.upper()))
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    # Set specific loggers to reduce noise
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance for a specific module

    Args:
        name: Name of the logger (typically __name__)

    Returns:
        Logger instance

    Example:
        logger = get_logger(__name__)
        logger.info("This is an info message")
    """
    return logging.getLogger(name)
