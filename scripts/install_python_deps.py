from __future__ import annotations

import argparse
import sys

import local_runtime_manager


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Install or refresh the local Python environment for PMS.")
    parser.add_argument(
        "--install-dev",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Install the project with dev extras and local AI extras (pytest, pytest-asyncio, sentence-transformers, faster-whisper).",
    )
    parser.add_argument(
        "--copy-env",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Copy .env.example to .env when .env is missing.",
    )
    parser.add_argument(
        "--verify",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Verify key modules after installation.",
    )
    parser.add_argument("--run-check", action="store_true", help="Run runtime config validation after installation.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    return local_runtime_manager._run_python_dependency_setup(args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
