from __future__ import annotations

import argparse
import logging
import sys

from .console import ColorFormatter, banner
from .config import load_config
from .factory import create_source, create_target
from .migrator import Migrator


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Migrate database tables and data.")
    parser.add_argument(
        "--config",
        default="config.yaml",
        help="Path to YAML config file. Default: config.yaml",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Console log level.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview tables and actions without creating, dropping, or copying data.",
    )
    return parser.parse_args()


def configure_logging(level: str) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(
        ColorFormatter(
            "%(asctime)s %(levelname)s %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    logging.basicConfig(level=getattr(logging, level), handlers=[handler])


def main() -> None:
    args = parse_args()
    configure_logging(args.log_level)
    print(banner(args.dry_run), file=sys.stderr)

    source = None
    target = None
    try:
        config = load_config(args.config)
        source = create_source(config.source)
        target = create_target(config.target)
        Migrator(source, target, config.options, dry_run=args.dry_run).run()
    except Exception as exc:
        logging.exception("Migration failed: %s", exc)
        sys.exit(1)
    finally:
        if source is not None:
            source.close()
        if target is not None:
            target.close()
