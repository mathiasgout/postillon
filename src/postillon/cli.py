"""The `postillon` command: `api`, `worker` and `migrate` (see docs/run-the-service.md)."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import uvicorn
from dotenv import load_dotenv
from pydantic import ValidationError

from postillon.api.app import create_app
from postillon.db.session import connect, migrate
from postillon.settings import Settings
from postillon.worker.main import run


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="postillon")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("postillon.toml"),
        help="the configuration file, whose folder holds `.env` and a relative `data_dir`",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    api = commands.add_parser("api", help="serve the HTTP API")
    api.add_argument("--host", default="127.0.0.1", help="address to listen on, 0.0.0.0 for the local network")
    api.add_argument("--port", type=int, default=8000, help="port to listen on")
    commands.add_parser("worker", help="publish the submitted entries")
    commands.add_parser("migrate", help="bring the database schema to the latest version")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    # The secrets live in `.env` next to the configuration file, never in the file itself.
    load_dotenv(args.config.parent / ".env")
    try:
        settings = Settings.load(args.config)
        match args.command:
            case "api":
                uvicorn.run(create_app(settings), host=args.host, port=args.port, log_config=None)
            case "worker":
                run(settings)
            case "migrate":
                migrate(connect(settings.database), settings.videos_dir)
    except (ValidationError, ValueError, OSError) as e:
        parser.exit(2, f"postillon: {e}\n")
