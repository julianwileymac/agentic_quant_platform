"""Operator entrypoint: ``aqp-bots-operator run``.

Runs the kopf event loop with all 9 CRD handlers registered. The
container's command in the operator Deployment manifest is:

    aqp-bots-operator run --namespace aqp-bots

(or omit ``--namespace`` for cluster-wide reconciliation).
"""
from __future__ import annotations

import argparse
import logging
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="aqp-bots-operator",
        description="QuantBot Platform Kubernetes Operator (kopf).",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    run = sub.add_parser("run", help="Start the operator event loop")
    run.add_argument(
        "--namespace",
        default=None,
        help="Restrict to a single namespace (defaults to cluster-wide).",
    )
    run.add_argument(
        "--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"]
    )

    args = parser.parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if args.cmd != "run":
        parser.print_help()
        return 2

    try:
        import kopf  # type: ignore[import-not-found]
    except ImportError:
        sys.stderr.write(
            "kopf is required for the operator; install with 'pip install kopf'\n"
        )
        return 3

    from aqp_bots.operator.handlers import register_handlers
    from aqp_bots.operator.webhooks import register_webhooks

    if not register_handlers():
        sys.stderr.write("failed to register operator handlers\n")
        return 4
    register_webhooks()  # webhooks are optional; failure logs but doesn't abort

    namespaces = [args.namespace] if args.namespace else None
    kopf.configure(verbose=args.log_level == "DEBUG")  # type: ignore[attr-defined]
    kopf.run(  # type: ignore[attr-defined]
        clusterwide=namespaces is None,
        namespaces=namespaces,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
