# Phase 0 docs migration — three external stragglers (2026-05-25)

> Owner of follow-up: a non-`aqp-index-curator` subagent or human
> operator. Triggered while the curator was running its
> `aqp-index-debt-docusaurus-restructure.md` pass.

## Why this exists

While verifying my Phase 0 refresh of `aqp_index/` per the procedure
in
[../../aqp_index/skills/aqp-index-curator-skill.md](../../aqp_index/skills/aqp-index-curator-skill.md),
I ran `bash aqp_docs/scripts/check-doc-links.sh` first with the
`--glob "!aqp_index/**"` exclusion removed, then again with the
exclusion restored. Both runs surface seven identical legacy-link
hits in three files **outside** the `aqp_index/` sole-writer boundary.
The curator cannot touch any of these; this note hands them off to
the right owner.

These hits would already have been failing the
[`aqp_docs/scripts/check-doc-links.sh`](../../aqp_docs/scripts/check-doc-links.sh)
guard on the Phase 0 PR before the curator ran. The debt note for
the curator
([aqp-index-debt-docusaurus-restructure.md](aqp-index-debt-docusaurus-restructure.md))
stated "the rest of the repo can stay green while the curator runs",
but the script's actual output shows it fails on these three files
regardless of whether the `aqp_index/**` exclusion is in place.

## What still drifts

| File | Line | Drift | Likely owner |
| --- | --- | --- | --- |
| [`aqp_ui/AGENTS.md`](../../aqp_ui/AGENTS.md) | 138 | Legacy `aqp_docs/<slug>.md` link to `tenancy-strategies.md`. Slug is **not** in `CONCEPT_MAPPING` in [`aqp_docs/scripts/migrate-content.py`](../../aqp_docs/scripts/migrate-content.py); it may have been renamed (closest candidate: `multi-tenancy.md` under `concepts/identity/`) or removed during Phase 0. | `aqp_ui` boundary owner; resolve the slug first, then rewrite the link. |
| [`webui/app/(shell)/docs/page.tsx`](../../webui/app/(shell)/docs/page.tsx) | 46-51 | Six legacy `aqp_docs/<slug>.md` references inside JSX `<code>` tags (`data-plane`, `backtest-engines`, `ml-framework`, `factor-research`, `strategy-lifecycle`, `observability`). All six slugs **are** in `CONCEPT_MAPPING`. The migration sweep at [`aqp_docs/scripts/sweep-links.py`](../../aqp_docs/scripts/sweep-links.py) intentionally skipped `webui/` (it is the legacy Next.js 15 surface retained for rollback only). | Either (a) rewrite the six paths so the legacy doc surface still renders sensibly during a rollback, or (b) add `--glob "!webui/**"` to the CI guard given the rollback-only status. |
| [`aqp_platform/deployments/kubernetes/base-services/redis-shared/secret.yaml`](../../aqp_platform/deployments/kubernetes/base-services/redis-shared/secret.yaml) | 13 | YAML comment referencing `aqp_docs/redis-stack.md`. Slug is **not** in `CONCEPT_MAPPING`; the doc may not exist in the new tree at all. | `aqp_platform` infra owner; confirm whether a `redis-stack.md` doc still exists under the new IA (none of `concepts/data/redpanda.md`, `phoenix.md`, `streaming.md`, `streaming-admin.md` directly replace it) and either rewrite the comment or remove it. |

## Why the migration sweep missed them

[`aqp_docs/scripts/sweep-links.py`](../../aqp_docs/scripts/sweep-links.py)
has three relevant gaps:

1. Its frontend-tree sweep targets `aqp_ui/src/`, not `aqp_ui/AGENTS.md`
   at the package root — `aqp_ui/AGENTS.md` is outside the swept set.
2. It deliberately excludes `webui/` because `webui/` is the legacy
   client retained for rollback only. The `check-doc-links.sh` guard
   does **not** mirror this exclusion, so the rollback-only surface
   still fails the check.
3. When the script encounters a slug that is not in `CONCEPT_TARGETS`
   (here: `tenancy-strategies`, `redis-stack`), it returns
   `match.group(0)` unchanged — that is the intended "unknown ->
   leave alone; reviewer follow-up" branch — so neither slug was
   rewritten.

## What the curator did NOT do

- I did **not** edit any of those three files. The
  [`aqp_index/AGENTS.md`](../../aqp_index/AGENTS.md) sole-writer rule
  is absolute outside the one documented exception (a one-liner pointer
  in repo-root `README.md` or `AGENTS.md`).
- I did **not** add a `--glob "!webui/**"` exclusion to
  [`aqp_docs/scripts/check-doc-links.sh`](../../aqp_docs/scripts/check-doc-links.sh).
  That is a policy decision (does CI scan rollback-only surfaces or
  not?) and belongs to the docs / infra owners, not the index curator.

## Suggested resolution path

1. The `aqp_ui` owner picks the right replacement for the
   `tenancy-strategies` link in `aqp_ui/AGENTS.md:138` and rewrites it
   (or removes the line if the doc is permanently gone).
2. The docs / frontend team decides webui's CI status — either fix
   the six links in `webui/app/(shell)/docs/page.tsx` (preserves CI
   parity even during rollback) or add the `webui/**` exclusion to the
   CI guard.
3. The `aqp_platform` infra owner resolves the `redis-stack` reference
   in the Redis secret YAML comment.
4. Once all three are resolved, re-run
   `bash aqp_docs/scripts/check-doc-links.sh` — it should then exit 0
   without further changes.

## Provenance

- Discovered during the curator's Phase 0 refresh pass driven by
  [aqp-index-debt-docusaurus-restructure.md](aqp-index-debt-docusaurus-restructure.md)
  (deleted in the same change set per the original debt note's
  instructions).
- Source: re-run of `bash aqp_docs/scripts/check-doc-links.sh` from
  the repo root after the curator's `aqp_index/` refresh landed.
