"""Addon-scoped logger.

Writes to `user_files/log/local_tts.log` inside the addon folder, so users
can tail it without restarting Anki. Module-level so every file does
`from ._log import log` and gets the same configured logger.
"""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

log = logging.getLogger("local_tts")


def configure(addon_dir: Path) -> None:
    """Attach a rotating file handler. Idempotent — safe to call repeatedly."""
    if any(isinstance(h, RotatingFileHandler) for h in log.handlers):
        return
    log_dir = addon_dir / "user_files" / "log"
    log_dir.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        log_dir / "local_tts.log", maxBytes=512_000, backupCount=2, encoding="utf-8"
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    log.addHandler(handler)
    log.setLevel(logging.DEBUG)
    log.propagate = False
