# radar.logging_setup
# ===================
#
# Central logging for PondEyes. One call to setup_logging() wires a rotating file handler
# (run-logs/pondeyes.log, git-ignored) plus a stderr handler, so:
#   - a human sees verbose output in the terminal, and
#   - an agent can tail/grep run-logs/pondeyes.log to diagnose issues (e.g. data-stream loss).
#
# Level is INFO by default; set PONDEYES_LOG=DEBUG for per-frame detail. Modules get a logger
# via get_logger(__name__-ish) and log through it — never print().

from __future__ import annotations

import logging
import logging.handlers
import os
from pathlib import Path

from radar.constants import ROOT

LOG_DIR = ROOT / "run-logs"
LOG_FILE = LOG_DIR / "pondeyes.log"

_configured = False


def get_logger(name: str = "pondeyes") -> logging.Logger:
    # All app loggers live under the "pondeyes" root so one config controls them.
    return logging.getLogger(name if name.startswith("pondeyes") else f"pondeyes.{name}")


def setup_logging(level: str | None = None) -> logging.Logger:
    # Idempotent: safe to call more than once. Honors PONDEYES_LOG env (default INFO).
    global _configured
    root = logging.getLogger("pondeyes")
    if _configured:
        return root

    LOG_DIR.mkdir(exist_ok=True)
    level_name = (level or os.environ.get("PONDEYES_LOG", "INFO")).upper()
    root.setLevel(getattr(logging, level_name, logging.INFO))

    fmt = logging.Formatter("%(asctime)s.%(msecs)03d %(levelname)-7s %(name)s: %(message)s",
                            "%H:%M:%S")

    # Rotating file: 2 MB x 5 keeps a useful window without unbounded growth.
    fh = logging.handlers.RotatingFileHandler(LOG_FILE, maxBytes=2_000_000, backupCount=5)
    fh.setFormatter(fmt)
    root.addHandler(fh)

    sh = logging.StreamHandler()      # stderr — visible in the terminal
    sh.setFormatter(fmt)
    root.addHandler(sh)

    root.propagate = False
    _configured = True
    root.info("logging initialised (level=%s) -> %s", level_name, LOG_FILE)
    return root
