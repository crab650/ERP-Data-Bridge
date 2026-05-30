from __future__ import annotations

import logging
import os
import sys


RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
CYAN = "\033[36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
MAGENTA = "\033[35m"
BLUE = "\033[34m"


def supports_color() -> bool:
    if os.getenv("NO_COLOR"):
        return False
    if os.getenv("TERM") == "dumb":
        return False
    return sys.stderr.isatty() or os.name == "nt"


def color(text: str, code: str) -> str:
    if not supports_color():
        return text
    return f"{code}{text}{RESET}"


def banner(dry_run: bool) -> str:
    mode = "DRY RUN" if dry_run else "LIVE MIGRATION"
    mode_color = YELLOW if dry_run else GREEN
    lines = [
        color("ERP DATA BRIDGE", f"{BOLD}{CYAN}"),
        color(f"Mode: {mode}", mode_color),
    ]
    return "\n".join(lines)


class ColorFormatter(logging.Formatter):
    LEVEL_COLORS = {
        logging.DEBUG: DIM,
        logging.INFO: CYAN,
        logging.WARNING: YELLOW,
        logging.ERROR: RED,
        logging.CRITICAL: f"{BOLD}{RED}",
    }

    def format(self, record: logging.LogRecord) -> str:
        original_levelname = record.levelname
        level_color = self.LEVEL_COLORS.get(record.levelno, RESET)
        record.levelname = color(f"{record.levelname:<7}", level_color)
        try:
            message = super().format(record)
        finally:
            record.levelname = original_levelname

        replacements = {
            "DRY RUN": color("DRY RUN", YELLOW),
            "Finished": color("Finished", GREEN),
            "Verified": color("Verified", GREEN),
            "Skipping": color("Skipping", YELLOW),
            "failed": color("failed", RED),
            "mismatch": color("mismatch", RED),
        }
        for plain, styled in replacements.items():
            message = message.replace(plain, styled)
        return message
