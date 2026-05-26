"""Render the nightly-backtest Step Function definition from configs/strategies/.

Usage:

    python -m scripts.render_nightly_sfn \\
        --strategies configs/strategies \\
        --invoke-arn 'arn:aws:lambda:us-east-1:1234:function:aqp-backtest-prod' \\
        --concurrency 5 \\
        --output infrastructure/sfn-nightly-backtest.json

The emitted definition uses ``Map`` with ``ItemProcessor`` (the
distributed map mode) so up to ``--concurrency`` strategies run in
parallel against the AQP backend Lambda. Each iteration POSTs
``{strategy: <slug>}`` to the AQP backend; the Lambda then enqueues
the matching ``aqp.tasks.backtest_tasks.run_backtest`` Celery task and
returns the task id, which AgentCore -> AQP polling can attach to via
the canonical ``/ws/backtest/runs/<id>`` WebSocket.

Why this lives at ``scripts/`` instead of inside the SFN module
itself: HashiCorp's archive_file provider doesn't let us shell out
during ``terraform plan``, and we want the rendered JSON committed +
diffable in PRs (so policy review sees the strategy list change before
apply lands the new SFN body).

This same script powers the ``aqp deploy aws --render-sfn`` CLI shim;
the operator runs it pre-merge, commits the JSON output, and the
``aqp_platform/terraform/environments/live`` Terraform reads it via
``file()`` -> ``var.nightly_state_machine_definition_json``.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


def _slugify(stem: str) -> str:
    return stem.lower().replace("_", "-").replace(" ", "-").strip("-")


def discover_strategies(root: Path) -> list[dict[str, Any]]:
    """Return ``[{slug, name, source_path}]`` for every YAML in ``root``.

    Skips templates / examples (filenames containing ``template`` or
    ``example``) so the nightly Map iterates real strategies only.
    Operators that want to include a template add an explicit
    ``aqp.io/include-in-nightly: true`` annotation at the YAML root.
    """
    out: list[dict[str, Any]] = []
    for path in sorted(root.glob("*.yaml")):
        stem = path.stem
        try:
            doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception:
            logger.warning("Skipping %s — not valid YAML", path.name)
            continue
        annotations = doc.get("annotations") or {}
        opt_in = bool(annotations.get("aqp.io/include-in-nightly"))
        if not opt_in and any(
            tag in stem.lower() for tag in ("template", "example", "quickstart")
        ):
            continue
        name = doc.get("name") or doc.get("strategy") or stem
        out.append(
            {
                "slug": _slugify(stem),
                "name": str(name),
                "source_path": str(path.as_posix()),
            }
        )
    return out


def build_definition(
    *,
    strategies: list[dict[str, Any]],
    invoke_lambda_arn: str,
    concurrency: int,
    task_timeout_seconds: int = 1800,
    retry_max_attempts: int = 2,
    retry_backoff_rate: float = 2.0,
) -> dict[str, Any]:
    """Build the Step Functions ASL definition for the nightly map.

    Top-level shape:

    .. code-block:: text

        StartAt: DispatchNightly
        States:
          DispatchNightly:
            Type: Map
            ItemsPath: $.strategies
            MaxConcurrency: <concurrency>
            ItemProcessor:                    (distributed map)
              StartAt: BacktestOne
              States:
                BacktestOne:
                  Type: Task
                  Resource: arn:aws:states:::lambda:invoke
                  Retry: [ ... ]
                  End: true
            End: true
    """
    if not strategies:
        # Empty registry -> a single Succeed state so terraform apply
        # still produces a valid SFN body.
        return {
            "Comment": "AQP nightly backtest — no strategies discovered.",
            "StartAt": "NoStrategies",
            "States": {"NoStrategies": {"Type": "Succeed"}},
        }
    return {
        "Comment": "AQP nightly backtest fan-out (rendered from configs/strategies/).",
        "StartAt": "DispatchNightly",
        "States": {
            "DispatchNightly": {
                "Type": "Map",
                "ItemsPath": "$.strategies",
                "MaxConcurrency": int(concurrency),
                "ItemSelector": {
                    "strategy_slug.$": "$$.Map.Item.Value.slug",
                    "strategy_name.$": "$$.Map.Item.Value.name",
                    "source_path.$": "$$.Map.Item.Value.source_path",
                    "execution_id.$": "$$.Execution.Id",
                },
                "ItemProcessor": {
                    "ProcessorConfig": {
                        "Mode": "DISTRIBUTED",
                        "ExecutionType": "STANDARD",
                    },
                    "StartAt": "BacktestOne",
                    "States": {
                        "BacktestOne": {
                            "Type": "Task",
                            "Resource": "arn:aws:states:::lambda:invoke",
                            "Parameters": {
                                "FunctionName": invoke_lambda_arn,
                                "Payload.$": "$",
                            },
                            "TimeoutSeconds": int(task_timeout_seconds),
                            "Retry": [
                                {
                                    "ErrorEquals": [
                                        "Lambda.ServiceException",
                                        "Lambda.AWSLambdaException",
                                        "Lambda.SdkClientException",
                                        "Lambda.TooManyRequestsException",
                                    ],
                                    "IntervalSeconds": 5,
                                    "MaxAttempts": int(retry_max_attempts),
                                    "BackoffRate": float(retry_backoff_rate),
                                },
                                {
                                    "ErrorEquals": ["States.Timeout"],
                                    "IntervalSeconds": 30,
                                    "MaxAttempts": 1,
                                    "BackoffRate": 1.0,
                                },
                            ],
                            "Catch": [
                                {
                                    "ErrorEquals": ["States.ALL"],
                                    "ResultPath": "$.error",
                                    "Next": "RecordFailure",
                                }
                            ],
                            "ResultPath": "$.result",
                            "End": True,
                        },
                        "RecordFailure": {
                            "Type": "Pass",
                            "Parameters": {
                                "strategy_slug.$": "$.strategy_slug",
                                "status": "failed",
                                "error.$": "$.error",
                            },
                            "End": True,
                        },
                    },
                },
                "End": True,
            }
        },
    }


def render_payload(strategies: list[dict[str, Any]]) -> dict[str, Any]:
    """Build the SFN execution payload Operators pass in via ``StartExecution``."""
    return {"strategies": strategies}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--strategies",
        type=Path,
        default=Path("configs/strategies"),
        help="Directory containing strategy YAML files.",
    )
    parser.add_argument(
        "--invoke-arn",
        required=True,
        help="ARN of the AQP backend Lambda the SFN calls per strategy.",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=5,
        help="MaxConcurrency for the Map state.",
    )
    parser.add_argument(
        "--task-timeout-seconds",
        type=int,
        default=1800,
        help="Per-strategy task timeout.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("infrastructure/sfn-nightly-backtest.json"),
        help="Output JSON path (the SFN module reads this via file()).",
    )
    parser.add_argument(
        "--payload-output",
        type=Path,
        default=None,
        help="Optional path to also dump the execution-payload JSON.",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    strategies = discover_strategies(args.strategies)
    logger.info(
        "Discovered %d strategy/-ies under %s", len(strategies), args.strategies
    )
    definition = build_definition(
        strategies=strategies,
        invoke_lambda_arn=args.invoke_arn,
        concurrency=args.concurrency,
        task_timeout_seconds=args.task_timeout_seconds,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(definition, indent=2), encoding="utf-8")
    logger.info("Wrote SFN definition -> %s", args.output)

    if args.payload_output:
        args.payload_output.parent.mkdir(parents=True, exist_ok=True)
        args.payload_output.write_text(
            json.dumps(render_payload(strategies), indent=2), encoding="utf-8"
        )
        logger.info("Wrote payload sample -> %s", args.payload_output)

    return 0


if __name__ == "__main__":  # pragma: no cover - script entrypoint
    sys.exit(main())


__all__ = [
    "build_definition",
    "discover_strategies",
    "main",
    "render_payload",
]
