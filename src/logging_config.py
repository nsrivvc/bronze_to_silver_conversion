"""
logging_config.py
=================
One place to configure logging. Import and call configure_logging() once at
process start (run.py does this). Logs go to stdout, which is what GitHub
Actions / Azure Container Apps / most schedulers capture automatically.
"""

from __future__ import annotations

import logging

from .config import settings

_CONFIGURED = False


def configure_logging() -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    configure_logging()
    return logging.getLogger(name)
