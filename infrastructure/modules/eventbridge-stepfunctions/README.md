# `modules/eventbridge-stepfunctions`

Three primary outputs:

1. **Step Function** `aqp-nightly-backtest-${env}` — fan-runs every
   strategy listed in `configs/strategies/` and posts results to the
   AQP API.
2. **EventBridge cron** that triggers the SFN on weekdays after US
   close (configurable via `var.nightly_cron_expression`).
3. **EventBridge S3 ObjectCreated rule** that routes to an operator-
   supplied Lambda to start a Bedrock KB ingestion job (lazy
   re-indexing when research docs are dropped into the KB source
   bucket).

The Step Function definition JSON is parameter-driven via
`var.state_machine_definition_json` so the consumer composition (or
a sibling script) can render it from the current
`configs/strategies/` listing without re-baking this module.

## Wiring contract

| SSM parameter                          | Purpose                                                   |
| -------------------------------------- | --------------------------------------------------------- |
| `/aqp/${env}/nightly_sfn_arn`          | Read by the `data.orchestration.*` MCP tools.             |
| `/aqp/${env}/nightly_rule_arn`         | Audit cross-reference for EventBridge dashboard.          |
