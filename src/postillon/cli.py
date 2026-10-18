"""The `postillon` command, for the service side (see docs/run-the-service.md)."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from postillon import environment
from postillon.adapter import login
from postillon.config import load_config
from postillon.service import Service


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="postillon")
    commands = parser.add_subparsers(dest="command", required=True)
    serve = commands.add_parser("serve", help="publish the entries of the configured projects")
    serve.add_argument("--config", type=Path, default=Path("postillon.toml"), help="configuration file")
    serve.add_argument("--once", action="store_true", help="run a single pass, then exit")
    connect = commands.add_parser("login", help="authorize an account and save its secrets to .env")
    connect.add_argument("project")
    connect.add_argument("platform")
    connect.add_argument("account")
    connect.add_argument("--config", type=Path, default=Path("postillon.toml"), help="configuration file")
    args = parser.parse_args(argv)
    if args.command == "login":
        _login(parser, args)
        return

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


def _login(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    try:
        config = load_config(args.config)
        settings = config.projects.get(args.project, {}).get(args.platform, {}).get(args.account)
        if settings is None:
            raise ValueError(f"{args.project}.{args.platform}.{args.account} is not in {args.config}")
        environment.load()
        secrets = login(args.platform, args.account, settings)
    except ValueError as e:
        parser.exit(2, f"postillon: {e}\n")
    for name, value in secrets.items():
        path = environment.save(name, value)
        print(f"{name} saved to {path}")
