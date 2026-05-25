// changesets-dual-output.ts — split Changesets output into the
// technical CHANGELOG.md and the customer-facing
// docs/release-notes/<version>.mdx + Headway-compatible
// release-notes.json + email-newsletter snippets.
//
// Runs as part of the docs build:
//   1. `pnpm changeset:version` consumes the .changeset/*.md files
//      and writes the canonical CHANGELOG.md at the repo root.
//   2. THIS script reads .changeset/*.md (before consumption) and
//      classifies each entry by frontmatter `audience` into the
//      matching surface(s).
//
// Phase 5 of the migration plan.

import { readFileSync, writeFileSync, readdirSync, mkdirSync, existsSync } from 'node:fs';
import { join, resolve } from 'node:path';

type Changeset = {
  audience: 'customer' | 'technical' | 'both';
  breaking: boolean;
  packages: Record<string, 'major' | 'minor' | 'patch'>;
  summary: string;
  body: string;
  filename: string;
};

const REPO_ROOT = resolve(__dirname, '..', '..');
const CHANGESET_DIR = join(REPO_ROOT, '.changeset');
const DOCS_RELEASE_NOTES_DIR = join(REPO_ROOT, 'aqp_docs', 'docs', 'release-notes');
const HEADWAY_JSON = join(REPO_ROOT, 'aqp_docs', 'static', 'release-notes.json');

function parseChangeset(filename: string): Changeset | null {
  if (filename === 'README.md' || filename === 'config.json') return null;
  const path = join(CHANGESET_DIR, filename);
  const raw = readFileSync(path, 'utf-8');
  const match = raw.match(/^---\s*\n([\s\S]*?)\n---\s*\n([\s\S]*)$/);
  if (!match) return null;
  const [, fm, body] = match;
  const lines = fm.split('\n').filter((l) => l.trim());
  const packages: Record<string, 'major' | 'minor' | 'patch'> = {};
  let audience: Changeset['audience'] = 'both';
  let breaking = false;
  for (const line of lines) {
    const m = line.match(/^"?([^":]+)"?\s*:\s*(major|minor|patch|true|false|customer|technical|both)\s*$/);
    if (!m) continue;
    const [, key, value] = m;
    if (value === 'major' || value === 'minor' || value === 'patch') {
      packages[key] = value;
    } else if (key === 'audience') {
      audience = value as Changeset['audience'];
    } else if (key === 'breaking') {
      breaking = value === 'true';
    }
  }
  const trimmedBody = body.trim();
  const [summary, ...rest] = trimmedBody.split('\n\n');
  return {
    audience,
    breaking,
    packages,
    summary: summary.trim(),
    body: rest.join('\n\n').trim(),
    filename,
  };
}

function loadChangesets(): Changeset[] {
  if (!existsSync(CHANGESET_DIR)) return [];
  return readdirSync(CHANGESET_DIR)
    .filter((f) => f.endsWith('.md') && f !== 'README.md')
    .map((f) => parseChangeset(f))
    .filter((c): c is Changeset => c !== null);
}

function bumpKind(c: Changeset): 'major' | 'minor' | 'patch' {
  const values = Object.values(c.packages);
  if (values.includes('major') || c.breaking) return 'major';
  if (values.includes('minor')) return 'minor';
  return 'patch';
}

function customerNotesMdx(changesets: Changeset[], version: string): string {
  const today = new Date().toISOString().slice(0, 10);
  const customer = changesets.filter((c) => c.audience === 'customer' || c.audience === 'both');
  const breaking = customer.filter((c) => c.breaking);
  const features = customer.filter((c) => bumpKind(c) === 'minor' && !c.breaking);
  const fixes = customer.filter((c) => bumpKind(c) === 'patch' && !c.breaking);
  const lines: string[] = [
    '---',
    `title: 'Release ${version}'`,
    `summary: 'AQP customer release notes for ${version} (${today}).'`,
    'owner: docs-team',
    `last_reviewed: ${today}`,
    'audience: customer',
    `version: '${version}'`,
    '---',
    '',
    `# Release ${version}`,
    '',
  ];
  if (breaking.length > 0) {
    lines.push('## Breaking changes', '');
    for (const c of breaking) {
      lines.push(`- **${c.summary}**`);
      if (c.body) lines.push(`  ${c.body.replace(/\n/g, '\n  ')}`);
    }
    lines.push('');
  }
  if (features.length > 0) {
    lines.push('## New', '');
    for (const c of features) {
      lines.push(`- ${c.summary}`);
      if (c.body) lines.push(`  ${c.body.replace(/\n/g, '\n  ')}`);
    }
    lines.push('');
  }
  if (fixes.length > 0) {
    lines.push('## Fixes', '');
    for (const c of fixes) {
      lines.push(`- ${c.summary}`);
    }
    lines.push('');
  }
  return lines.join('\n');
}

function headwayFeed(changesets: Changeset[]): string {
  const customer = changesets.filter((c) => c.audience === 'customer' || c.audience === 'both');
  const entries = customer.map((c) => ({
    id: c.filename,
    title: c.summary,
    category: c.breaking ? 'breaking' : bumpKind(c) === 'minor' ? 'new' : 'improvement',
    body: c.body || c.summary,
    publishedAt: new Date().toISOString(),
    breaking: c.breaking,
  }));
  return JSON.stringify({ entries, generatedAt: new Date().toISOString() }, null, 2);
}

function main(): void {
  const changesets = loadChangesets();
  if (changesets.length === 0) {
    console.log('[changesets-dual-output] no changesets to process.');
    return;
  }
  const version = process.env.AQP_DOCS_RELEASE_VERSION ?? new Date().toISOString().slice(0, 10);
  mkdirSync(DOCS_RELEASE_NOTES_DIR, { recursive: true });
  writeFileSync(
    join(DOCS_RELEASE_NOTES_DIR, `${version}.mdx`),
    customerNotesMdx(changesets, version),
    'utf-8',
  );
  writeFileSync(HEADWAY_JSON, headwayFeed(changesets), 'utf-8');
  console.log(
    `[changesets-dual-output] wrote customer notes for ${version}.mdx (${changesets.length} changesets)`,
  );
}

main();
