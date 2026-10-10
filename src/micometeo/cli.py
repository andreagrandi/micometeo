"""Command line entry point."""

import argparse
import json
import sys
from pathlib import Path

from micometeo.config import ConfigError
from micometeo.runner import run_experiment


def find_root() -> Path:
    """Return the repository root, found by walking up to pyproject.toml."""
    for folder in [Path.cwd(), *Path.cwd().parents]:
        if (folder / "pyproject.toml").is_file() and (folder / "experiments").is_dir():
            return folder
    return Path.cwd()


def main(argv: list[str] | None = None) -> int:
    """Run the micometeo command line."""
    parser = argparse.ArgumentParser(prog="micometeo")
    commands = parser.add_subparsers(dest="command", required=True)
    run_parser = commands.add_parser("run", help="Run one experiment")
    run_parser.add_argument("experiment_name")
    args = parser.parse_args(argv)
    try:
        record_path = run_experiment(name=args.experiment_name, root=find_root())
    except (ConfigError, FileNotFoundError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2
    record = json.loads(record_path.read_text(encoding="utf-8"))
    print(f"Status: {record['status']}")
    if record["error"]:
        print(f"Error: {record['error']}")
    print(f"Run record: {record_path}")
    return 0 if record["status"] == "completed" else 1


if __name__ == "__main__":
    sys.exit(main())
