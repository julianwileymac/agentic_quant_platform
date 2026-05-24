# RTS 6 / SEC 15c3-5 Annual Validation Report

> Mechanical generation + sign-off workflow.
> Audience: Risk Management, Internal Audit, CEO, compliance counsel.

## Regulatory anchors

- **MiFID II RTS 6, Article 9** — "An investment firm shall annually
  perform a self-assessment and validation process and on the basis of
  that process issue a validation report... The risk management function
  shall draft the report; internal audit shall audit the report."
- **SEC Rule 15c3-5(e)** — "The broker or dealer shall regularly review
  the effectiveness of the risk management controls and supervisory
  procedures... The CEO shall certify annually that the firm's risk
  management controls and supervisory procedures comply with paragraphs
  (b) and (c) of this section."

## Generate the artifact

```bash
# CLI (single bot — usually just for testing the generator):
aqp-bots conformance <bot-slug>
aqp-bots stress <bot-slug>

# REST (fleet-wide):
curl -X POST https://api.aqp.io/bots/<slug>/conformance
curl -X POST https://api.aqp.io/bots/<slug>/stress
curl -X GET  https://api.aqp.io/bots/<slug>/risk/validation-report > validation-report.yaml
```

The artifact is a YAML document with three top-level sections:

1. **MiFID II RTS 6** — Article 6 / 9 / 10 / 12 / 15 / 16 / 17 results.
2. **SEC Rule 15c3-5** — (c)(1)(i)/(ii), (d), (e) results.
3. **Evidence** — embedded `bot_inventory`, `conformance_results`,
   `stress_results`, `kill_switch_drills`.

## Required attestations

The generator leaves three slots empty:

| Slot | Required by | Filled by |
| --- | --- | --- |
| `attestations.risk_management_function` | RTS 6 Art. 9(2) | Head of Risk |
| `attestations.internal_audit` | RTS 6 Art. 9(3) | Head of Internal Audit |
| `attestations.ceo_certification` | SEC 15c3-5(e) | CEO |

Sign-off is **operational, not mechanical**. The generator emits
unsigned YAML; the firm's compliance workflow fills in the slots and
adds digital signatures (e.g. via a Yubikey-backed signing pipeline).

## Cadence

- **Annual:** by 31 March each year, covering the previous calendar year.
- **Ad-hoc:** after any material control change (new policy, threshold
  retune, new venue, new asset class), generate a fresh artifact and
  re-circulate for sign-off.
- **Quarterly drill:** the kill-switch incident response runbook
  (separate doc) exercises the three-scope kill switch quarterly; that
  drill's evidence is included in the next annual report.

## Storage

- Signed YAML artifacts: `s3://aqp-compliance/validation-reports/<year>/`
  with object lock + WORM retention >= 7 years.
- The audit trail (who generated the artifact, when, with which inputs)
  is in `bot_events` (event_type=`validation_report.generated`).

## Caveat

This workflow is an **engineering crosswalk**, NOT legal advice. The
specific scope of "algorithmic trading" / "market access" for any given
firm is a legal determination that compliance counsel must make. The
generator only mechanizes the controls that are already implemented in
code.
