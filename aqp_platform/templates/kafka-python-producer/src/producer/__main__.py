"""CLI entrypoint - `python -m producer` runs the sample loop."""

from __future__ import annotations

from .app import run_sample


def main() -> None:
    run_sample()


if __name__ == "__main__":
    main()
