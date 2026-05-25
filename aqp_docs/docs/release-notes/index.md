---
title: 'Release notes'
summary: 'Customer-facing release notes for AQP. Generated from Changesets on every release.'
owner: docs-team
last_reviewed: 2026-05-25
audience: both
sidebar_position: 1
---

# Release notes

Customer-facing release notes for the Agentic Quant Platform. New
entries land here whenever a PR's Changeset is marked
`audience: customer` or `audience: both` (see
[`.changeset/README.md`](https://github.com/julianwileymac/agentic_quant_platform/blob/main/.changeset/README.md)).

For the full technical changelog (every commit, including
non-customer-facing internal refactors), see
[CHANGELOG.md](https://github.com/julianwileymac/agentic_quant_platform/blob/main/CHANGELOG.md).

## Subscribe

- **RSS / Atom feed**: built from this folder by Docusaurus —
  available at [/blog/rss.xml](/blog/rss.xml).
- **In-product changelog widget**: powered by
  [`/release-notes.json`](/release-notes.json) (Headway-compatible).
- **Email digest**: opt in from the operator UI profile menu.

## API epochs

AQP uses Stripe-style date-epoch API versioning. New epochs:

- Roll out on the first of the month (`2026-06-01`, `2026-09-01`, …).
- Preserve old contracts via the `Deprecation` / `Sunset` HTTP
  headers (RFC 8594) for a 12-month sunset cycle.
- Move to [archive.aqp.fund](https://archive.aqp.fund) when fully
  retired.

The matching reference docs live at
[/reference/api/](../reference/api/index.mdx).
