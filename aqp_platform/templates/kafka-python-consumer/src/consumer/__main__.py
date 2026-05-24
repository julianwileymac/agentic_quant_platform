"""CLI entrypoint - `python -m consumer` starts the async loop."""

from __future__ import annotations

import asyncio

from .app import run_forever


def main() -> None:
    asyncio.run(run_forever())


if __name__ == "__main__":
    main()
