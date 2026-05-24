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

from aqp_bots.base import build_bot
from aqp_bots.registry import get_bot_spec, list_bot_specs
from aqp_bots.runtime import BotRuntime

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

    replay = sub.add_parser("replay", help="Time-travel replay of bot_events for a bot")
    replay.add_argument("slug")
    replay.add_argument("--since-seq", type=int, default=0)
    replay.add_argument("--until-seq", type=int, default=None)
    replay.add_argument("--limit", type=int, default=None)

    conformance = sub.add_parser(
        "conformance",
        help="Run the RTS 6 Article 6 conformance test harness",
    )
    conformance.add_argument("slug")

    stress = sub.add_parser(
        "stress",
        help="Run the RTS 6 Article 10 stress test (2x prior 6-month peak)",
    )
    stress.add_argument("slug")
    stress.add_argument("--duration-s", type=float, default=5.0)
    stress.add_argument("--rate-multiplier", type=float, default=2.0)

    render = sub.add_parser(
        "render-manifest",
        help="Preview the operator-rendered k8s manifests for a bot (no apply)",
    )
    render.add_argument("slug")

    validate = sub.add_parser(
        "validate",
        help="Run the validating-webhook checks locally on a bot spec",
    )
    validate.add_argument("slug")

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


def _replay(slug: str, since_seq: int, until_seq: int | None, limit: int | None) -> int:
    """Replay bot_events for the bot identified by ``slug``."""
    from aqp_bots.state.replay import replay_events

    captured: list[dict[str, Any]] = []

    def _capture_any(_event_data: dict[str, Any]) -> None:
        captured.append(_event_data)

    spec = get_bot_spec(slug)
    bot_id = spec.slug or spec.name
    cursor = replay_events(
        bot_id=bot_id,
        handlers={"order": _capture_any, "fill": _capture_any, "snapshot": _capture_any},
        since_seq=since_seq,
        until_seq=until_seq,
        limit=limit,
    )
    print(
        json.dumps(
            {
                "bot_id": cursor.bot_id,
                "events_seen": cursor.events_seen,
                "final_seq_no": cursor.final_seq_no,
                "skipped_event_types": sorted(set(cursor.skipped)),
                "errors": cursor.errors,
            },
            indent=2,
            default=str,
        )
    )
    return 0 if not cursor.errors else 1


def _conformance(slug: str) -> int:
    """Run the RTS 6 Article 6 conformance harness against the bot's risk engine."""
    from aqp_bots.risk.engine import PreTradeRiskEngine
    from aqp_bots.risk.policies import (
        MaxOrderValuePolicy,
        MaxOrderVolumePolicy,
        PriceCollarPolicy,
    )
    from aqp_bots.risk.reg.conformance import run_conformance_tests
    from decimal import Decimal as _Decimal

    spec = get_bot_spec(slug)
    rl = spec.risk_layer
    engine = PreTradeRiskEngine(
        policies=[
            PriceCollarPolicy(max_bps=int((rl.price_collar_bps if rl else None) or 100)),
            MaxOrderValuePolicy(
                max_value_usd=_Decimal(str((rl.max_order_value_usd if rl else None) or "100000"))
            ),
            MaxOrderVolumePolicy(
                max_qty=_Decimal(str((rl.max_order_qty if rl else None) or "10000"))
            ),
        ],
        check_kill_switch=False,
        check_legacy_risk_manager=False,
    )
    result = run_conformance_tests(engine=engine)
    print(
        json.dumps(
            {
                "bot": slug,
                "cases_run": result.cases_run,
                "cases_passed": result.cases_passed,
                "cases_failed": result.cases_failed,
                "passing": result.is_passing(),
            },
            indent=2,
            default=str,
        )
    )
    return 0 if result.is_passing() else 1


def _stress(slug: str, duration_s: float, rate_multiplier: float) -> int:
    """Run the RTS 6 Article 10 stress test against the bot's risk engine."""
    from aqp_bots.risk.engine import PreTradeRiskEngine
    from aqp_bots.risk.policies import MaxOrderValuePolicy, MaxOrderVolumePolicy
    from aqp_bots.risk.reg.stress import run_stress_test
    from decimal import Decimal as _Decimal

    spec = get_bot_spec(slug)
    rl = spec.risk_layer
    engine = PreTradeRiskEngine(
        policies=[
            MaxOrderValuePolicy(
                max_value_usd=_Decimal(str((rl.max_order_value_usd if rl else None) or "100000"))
            ),
            MaxOrderVolumePolicy(
                max_qty=_Decimal(str((rl.max_order_qty if rl else None) or "10000"))
            ),
        ],
        check_kill_switch=False,
        check_legacy_risk_manager=False,
    )
    result = run_stress_test(
        engine=engine,
        bot_id=slug,
        duration_s=duration_s,
        rate_multiplier=rate_multiplier,
    )
    print(
        json.dumps(
            {
                "bot": slug,
                "target_rate_per_s": result.target_rate_per_s,
                "throughput_per_s": result.throughput_per_s,
                "messages_sent": result.messages_sent,
                "blocks": result.blocks,
                "warnings": result.warnings,
                "allows": result.allows,
                "passed": result.passed,
            },
            indent=2,
            default=str,
        )
    )
    return 0 if result.passed else 1


def _render_manifest(slug: str) -> int:
    """Preview the operator-rendered manifests for ``slug``."""
    import yaml

    spec = get_bot_spec(slug)
    if spec.capabilities is None:
        # Legacy bot — fall back to the existing KubernetesTarget renderer.
        from aqp_bots.base import build_bot
        from aqp_bots.deploy import KubernetesTarget

        bot = build_bot(spec)
        manifest = KubernetesTarget().render_manifest(bot, overrides={})
        print(manifest)
        return 0
    from aqp_bots.operator.crds.bot_cr import BotCR, BotSpecField, CapabilitiesField
    from aqp_bots.operator.render import render_bot_workload

    caps = CapabilitiesField(
        frequency=spec.capabilities.frequency.value,
        assetClasses=[a.value for a in spec.capabilities.asset_classes],
        venues=list(spec.capabilities.venues),
        needsGpu=spec.capabilities.needs_gpu,
        needsNumaPinning=spec.capabilities.needs_numa_pinning,
        needsHugepagesMiB=spec.capabilities.needs_hugepages_mib,
        needsSrIov=spec.capabilities.needs_sr_iov,
        expectedP99TickToTradeUs=spec.capabilities.expected_p99_tick_to_trade_us,
        maxCapitalUsd=str(spec.capabilities.max_capital_usd),
    )
    bot_cr = BotCR(
        metadata={"name": spec.slug or spec.name, "namespace": spec.deployment.namespace},
        spec=BotSpecField(capabilities=caps, botSpec=spec.model_dump(mode="json")),
    )
    documents = render_bot_workload(bot_cr)
    print(yaml.safe_dump_all(documents, sort_keys=False))
    return 0


def _validate(slug: str) -> int:
    """Run the same validations the admission webhook does."""
    spec = get_bot_spec(slug)
    failures: list[str] = []
    if spec.capabilities is not None and spec.capabilities.frequency.value == "hft":
        if not spec.capabilities.needs_numa_pinning:
            failures.append("HFT bot must set capabilities.needs_numa_pinning=True")
        if spec.capabilities.expected_p99_tick_to_trade_us is None:
            failures.append("HFT bot must set capabilities.expected_p99_tick_to_trade_us")
    if spec.risk_layer and spec.risk_layer.max_order_value_usd is not None:
        try:
            if float(spec.risk_layer.max_order_value_usd) <= 0:
                failures.append("risk_layer.max_order_value_usd must be > 0")
        except (TypeError, ValueError):
            failures.append("risk_layer.max_order_value_usd must be numeric")
    print(
        json.dumps(
            {"bot": slug, "valid": not failures, "failures": failures},
            indent=2,
            default=str,
        )
    )
    return 0 if not failures else 1


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
    if args.cmd == "replay":
        return _replay(args.slug, args.since_seq, args.until_seq, args.limit)
    if args.cmd == "conformance":
        return _conformance(args.slug)
    if args.cmd == "stress":
        return _stress(args.slug, args.duration_s, args.rate_multiplier)
    if args.cmd == "render-manifest":
        return _render_manifest(args.slug)
    if args.cmd == "validate":
        return _validate(args.slug)
    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
