"""The `postillon` command, for the service side (see docs/run-the-service.md)."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from postillon.config import load_config
from postillon.service import Service


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="postillon")
    commands = parser.add_subparsers(dest="command", required=True)
    serve = commands.add_parser("serve", help="publish the entries of the configured projects")
    serve.add_argument("--config", type=Path, default=Path("postillon.toml"), help="configuration file")
    serve.add_argument("--once", action="store_true", help="run a single pass, then exit")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        config = load_config(args.config)
        service = Service.from_config(config)
    except ValueError as e:
        parser.exit(2, f"postillon: {e}\n")
    if args.once:
        service.run_pass()
        return
    try:
        service.run_forever(config.poll_seconds)
    except KeyboardInterrupt:
        pass
