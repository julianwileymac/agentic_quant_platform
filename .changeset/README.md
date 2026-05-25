# Changesets

This directory contains [Changesets](https://github.com/changesets/changesets)
release-note files for the Agentic Quant Platform.

## What goes here

One Markdown file per PR that introduces a customer-visible or
agent-visible change. Each file has frontmatter classifying the change
and a body that becomes the human-readable release-note bullet.

## Frontmatter contract

```markdown
---
"aqp": minor
audience: customer | technical | both
breaking: false
---

One-sentence summary of the change (customer-friendly).

Optional follow-up paragraph(s) with context, migration notes, or
links to the relevant documentation page.
```

- `audience: customer` -> emitted to `aqp_docs/docs/release-notes/<version>.mdx`
- `audience: technical` -> emitted to root `CHANGELOG.md`
- `audience: both` -> emitted to both surfaces

## Authoring

```powershell
pnpm changeset
```

The interactive prompt asks for the affected packages, the bump type
(major / minor / patch), and the summary. Commit the resulting file
with your PR.

## API breaking changes

If `oasdiff breaking` flags a PR, the PR MUST include a Changeset with
`breaking: true` and a migration paragraph. CI enforces this.

## References

- [`.changeset/config.json`](config.json) — Changeset configuration.
- [`aqp_docs/docs/release-notes/`](../aqp_docs/docs/release-notes/) — customer-facing release notes.
- [`CHANGELOG.md`](../CHANGELOG.md) — technical changelog.
