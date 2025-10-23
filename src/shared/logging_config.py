#!/usr/bin/env python3
"""
Centralized logging configuration for Boann
"""

import logging
import os


def setup_logging():
    """
    Configure logging for the entire application.
    This should be called once at application startup.
    """
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()

    # Configure root logger
    logging.basicConfig(
        level=getattr(logging, log_level),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        force=True,  # This ensures it overrides any existing configuration
    )

    # Set all loggers to the same level
    logging.getLogger().setLevel(getattr(logging, log_level))

    # When LOG_LEVEL=DEBUG, show third-party logs at INFO level to see their activity
    if log_level == "DEBUG":
        # Set third-party loggers to INFO level to see their activity during debugging
        logging.getLogger("httpcore").setLevel(logging.INFO)
        logging.getLogger("httpx").setLevel(logging.INFO)
        logging.getLogger("llama_stack_client").setLevel(logging.INFO)
        logging.getLogger("uvicorn").setLevel(logging.INFO)
        logging.getLogger("uvicorn.error").setLevel(logging.INFO)
        logging.getLogger("uvicorn.access").setLevel(logging.INFO)
    else:
        # For non-DEBUG levels, suppress noisy third-party loggers
        logging.getLogger("httpcore").setLevel(logging.WARNING)
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("llama_stack_client").setLevel(logging.WARNING)


def get_logger(name: str = None):
    """
    Get a logger instance.
    """
    return logging.getLogger(name or __name__)
