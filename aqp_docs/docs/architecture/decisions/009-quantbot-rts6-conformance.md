---
title: 'ADR 009 — MiFID II RTS 6 + SEC 15c3-5 Conformance'
summary: 'Algorithmic trading in EU markets is governed by Commission Delegated Regulation (EU) 2017/589 — **MiFID II Regulatory Technical Standards on the organisational requirements of investment firms engage...'
owner: platform-team
last_reviewed: 2026-05-25
audience: both
---

# ADR 009 — MiFID II RTS 6 + SEC 15c3-5 Conformance

**Status:** Accepted (QuantBot Platform v0.2.0)
**Date:** 2026-05-24
**LEGAL REVIEW REQUIRED.** This ADR + the code it documents are an
**engineering crosswalk**, NOT legal advice. Any production deployment
trading European or US equities (or directly-affected derivatives) requires
sign-off from the firm's compliance counsel and the CEO's annual
certification.

## Context

Algorithmic trading in EU markets is governed by Commission Delegated
Regulation (EU) 2017/589 — **MiFID II Regulatory Technical Standards
on the organisational requirements of investment firms engaged in
algorithmic trading** ("RTS 6"). US market access is governed by SEC
Rule 15c3-5 (17 CFR § 240.15c3-5).

Both regimes require pre-trade risk controls, kill functionality, real-
time reconciliation, conformance testing, stress testing, and annual
validation. The QuantBot Platform must:

1. Enforce every named control before an order leaves the bot.
2. Generate the annual validation report mechanically.
3. Document the required attestations the firm's officers must sign.

## Decision

- **Two-tier risk:** Layer-1 in-bot `PreTradeRiskEngine` for the
  latency-sensitive fast path; Layer-2 out-of-band FastAPI service
  for the broker-dealer-controlled aggregate-credit check (§ 240.15c3-5(d)).
- **Hard vs soft block:** policy verdicts carry `severity = "block"`
  (hard — order rejected) or `severity = "warn"` (soft — informational
  only, may be overridden). Mirrors the ESMA Supervisory Briefing
  §72 (hard) vs §75/§76 (soft) distinction.
- **Crosswalk:** every policy in `aqp_bots/risk/policies.py` carries a
  `citation` string. The `aqp_bots/risk/reg/rts6.py` and
  `rule_15c3_5.py` modules list the mapping by class name.
- **Kill switch (RTS 6 Art. 12):** three-scope (`bot` / `fleet` /
  `platform`) implementation in `aqp_bots/risk/kill_switch_v2.py`,
  backed by Redis + a `KillSwitch` CRD. Cancellation is immediate;
  affected bots transition to `Draining` and (optionally) flatten
  positions.
- **Real-time reconciliation (Art. 17(3)):** `ExecutionAdapter.reconcile()`
  is called on every reconnect; drop-copy ingest is the canonical
  real-time path; mismatches elevate to `OrderStatus.DISPUTED` and
  quarantine the strategy from new entries.
- **Real-time alerts (Art. 16(5)) — "within 5 seconds":**
  Prometheus Alertmanager rules with `interval: 15s` and `for: 0s`
  on critical signals (`prometheus-rules.yaml`).
- **Conformance testing (Art. 6):** `aqp_bots/risk/reg/conformance.py`
  ships a synthetic test harness; CLI `aqp-bots conformance <slug>` and
  REST `POST /bots/{ref}/conformance` run it on demand.
- **Stress testing (Art. 10) — "twice the volume of the highest
  volume...during the previous six months":** `aqp_bots/risk/reg/stress.py`
  reads the peak rate from `bot_events` and replays at 2x through the
  engine. CLI `aqp-bots stress <slug>` and REST `POST /bots/{ref}/stress`.
- **Annual validation (Art. 9 + § 240.15c3-5(e)):**
  `aqp_bots/risk/reg/validation_report.py` generates a YAML artifact
  with empty signature slots for risk management, internal audit, and
  the CEO. The generator runs daily as a Celery task; the artifact
  itself requires manual sign-off before submission.

## Attestation slots (left blank by the generator)

The validation report has three signature slots:

1. **Risk management function (RTS 6 Art. 9(2)):** drafts the report.
2. **Internal audit (RTS 6 Art. 9(3)):** audits the report.
3. **CEO certification (SEC 15c3-5(e)):** annual certification that
   the firm's risk management controls comply with paragraphs (b)
   and (c) of the rule.

The generator does NOT auto-sign these slots; that is operational, not
mechanical.

## Consequences

- **+** Every block has a regulatory citation.
- **+** Conformance + stress + annual validation are reproducible
  CI artifacts.
- **−** This is an engineering crosswalk; legal counsel must validate
  the mappings against the specific firm's regulatory perimeter.
- **−** Cross-asset firms (equity + futures + crypto) may need
  additional policies beyond what we ship out of the box.

## References

- Commission Delegated Regulation (EU) 2017/589 (MiFID II RTS 6)
- 17 CFR § 240.15c3-5 (SEC Rule 15c3-5)
- ESMA Supervisory Briefing on Algorithmic Trading (26 Feb 2026)
- [aqp_bots/risk/](../../../aqp_bots/risk/)
