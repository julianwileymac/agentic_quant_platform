"""``python -m aqp.bots.cli`` — operate bots from the shell.

Subcommands:

- ``list`` — list every bot the registry can see.
- ``show <slug>`` — pretty-print the spec and current version.
- ``backtest <slug>`` — run a single backtest synchronously.
- ``paper <slug>`` — run a paper session synchronously.
- ``chat <slug> <prompt>`` — drive a research bot (one turn).
- ``deploy <slug>`` — dispatch the configured deployment target.
- ``run <slug>`` — generic "do whatever the deployment says". Paper bots
  start a paper session; backtest-only bots run a backtest; k8s bots
  re-render their manifest (useful for the in-cluster pod entrypoint).

The CLI exists primarily so the Kubernetes manifest rendered by
:class:`aqp.bots.deploy.KubernetesTarget` has a stable command to run
in-pod (``python -m aqp.bots.cli run <slug>``).
"""
from __future__ import annotations

import argparse
import json
import logging
import sys

from aqp.bots.base import build_bot
from aqp.bots.registry import get_bot_spec, list_bot_specs
from aqp.bots.runtime import BotRuntime

logger = logging.getLogger(__name__)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="aqp-bots", description="Operate AQP bots from the shell.")
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("list", help="List every bot in the registry")

    show = sub.add_parser("show", help="Print a bot's spec")
    show.add_argument("slug")
    show.add_argument("--yaml", action="store_true", help="Print YAML instead of JSON")

    backtest = sub.add_parser("backtest", help="Run a single backtest synchronously")
    backtest.add_argument("slug")
    backtest.add_argument("--run-name", default=None)

    paper = sub.add_parser("paper", help="Run a paper session synchronously")
    paper.add_argument("slug")
    paper.add_argument("--run-name", default=None)

    chat = sub.add_parser("chat", help="Drive a single research bot turn")
    chat.add_argument("slug")
    chat.add_argument("prompt")
    chat.add_argument("--session-id", default=None)
    chat.add_argument("--agent-role", default=None)

    deploy = sub.add_parser("deploy", help="Dispatch the configured deployment target")
    deploy.add_argument("slug")
    deploy.add_argument("--target", default=None)

    run = sub.add_parser("run", help="Pod entrypoint — run whatever the deployment target says")
    run.add_argument("slug")

    return parser


def _list() -> int:
    specs = list_bot_specs()
    if not specs:
        print("(no bots registered)")
        return 0
    for spec in specs:
        print(f"{spec.slug}  [{spec.kind}]  {spec.name}")
    return 0


def _show(slug: str, *, as_yaml: bool) -> int:
    spec = get_bot_spec(slug)
    if as_yaml:
        print(spec.to_yaml())
    else:
        print(json.dumps(spec.model_dump(mode="json"), indent=2, default=str))
    return 0


def _runtime(slug: str) -> BotRuntime:
    spec = get_bot_spec(slug)
    bot = build_bot(spec)
    return BotRuntime(bot)


def _backtest(slug: str, run_name: str | None) -> int:
    runtime = _runtime(slug)
    result = runtime.backtest(run_name=run_name)
    print(json.dumps(result.to_dict(), indent=2, default=str))
    return 0 if result.status == "completed" else 1


def _paper(slug: str, run_name: str | None) -> int:
    runtime = _runtime(slug)
    result = runtime.paper(run_name=run_name)
    print(json.dumps(result.to_dict(), indent=2, default=str))
    return 0 if result.status == "completed" else 1


def _chat(slug: str, prompt: str, session_id: str | None, agent_role: str | None) -> int:
    runtime = _runtime(slug)
    result = runtime.chat(prompt, session_id=session_id, agent_role=agent_role)
    print(json.dumps(result.to_dict(), indent=2, default=str))
    return 0 if result.status == "completed" else 1


def _deploy(slug: str, target: str | None) -> int:
    runtime = _runtime(slug)
    result = runtime.deploy(target=target)
    print(json.dumps(result.to_dict(), indent=2, default=str))
    return 0 if result.status == "completed" else 1


def _run(slug: str) -> int:
    """Dispatch to the right subcommand based on the spec's deployment target."""
    spec = get_bot_spec(slug)
    target = spec.deployment.target
    if target == "paper_session":
        return _paper(slug, run_name=None)
    if target == "backtest_only":
        return _backtest(slug, run_name=None)
    if target == "kubernetes":
        # Pod is already running; default to paper_session if the spec also
        # has a strategy, otherwise just print the spec for debugging.
        if spec.strategy is not None and spec.kind == "trading":
            return _paper(slug, run_name=None)
        return _show(slug, as_yaml=False)
    print(f"unknown deployment target {target!r}", file=sys.stderr)
    return 2


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.cmd == "list":
        return _list()
    if args.cmd == "show":
        return _show(args.slug, as_yaml=args.yaml)
    if args.cmd == "backtest":
        return _backtest(args.slug, args.run_name)
    if args.cmd == "paper":
        return _paper(args.slug, args.run_name)
    if args.cmd == "chat":
        return _chat(args.slug, args.prompt, args.session_id, args.agent_role)
    if args.cmd == "deploy":
        return _deploy(args.slug, args.target)
    if args.cmd == "run":
        return _run(args.slug)
    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
