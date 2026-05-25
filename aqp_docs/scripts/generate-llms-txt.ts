// generate-llms-txt.ts — emit /llms.txt + /llms-full.txt at build time.
//
// llms.txt spec: https://llmstxt.org/
// Two artifacts:
//   - aqp_docs/static/llms.txt       — curated, structured index
//   - aqp_docs/static/llms-full.txt  — concatenated full corpus
//
// The docusaurus-plugin-llms-txt plugin emits similar output, but we
// shell our own here too so the format stays under our control (the
// plugin is opinionated about depth, ordering, and what to strip from
// MDX). Both outputs are served from /llms.txt and /llms-full.txt
// directly (see aqp_docs/static/_headers).
//
// Hard rules respected:
//   - aqp-management-engine always-on: never echo secrets in the
//     corpus. The audience: internal frontmatter filter is the gate.

import { readFileSync, readdirSync, statSync, writeFileSync, mkdirSync } from 'node:fs';
import { join, relative, resolve } from 'node:path';

type Frontmatter = {
  title?: string;
  summary?: string;
  owner?: string;
  audience?: string;
  last_reviewed?: string;
  deprecated?: boolean;
};

const REPO_ROOT = resolve(__dirname, '..', '..');
const DOCS_DIR = join(REPO_ROOT, 'aqp_docs', 'docs');
const STATIC_DIR = join(REPO_ROOT, 'aqp_docs', 'static');
const SITE_URL = process.env.AQP_DOCS_SITE_URL ?? 'https://docs.aqp.fund';

const EXCLUDE_DIRS = new Set(['internal', 'archive']);

function walk(dir: string): string[] {
  const out: string[] = [];
  for (const name of readdirSync(dir)) {
    const full = join(dir, name);
    const st = statSync(full);
    if (st.isDirectory()) {
      if (EXCLUDE_DIRS.has(name)) continue;
      out.push(...walk(full));
    } else if (st.isFile() && (name.endsWith('.md') || name.endsWith('.mdx'))) {
      out.push(full);
    }
  }
  return out;
}

function parseFrontmatter(content: string): { fm: Frontmatter; body: string } {
  const match = content.match(/^---\s*\n([\s\S]*?)\n---\s*\n([\s\S]*)$/);
  if (!match) return { fm: {}, body: content };
  const fmText = match[1];
  const body = match[2];
  const fm: Frontmatter = {};
  for (const line of fmText.split('\n')) {
    const kv = line.match(/^([a-zA-Z_]+):\s*(.*)$/);
    if (!kv) continue;
    const [, key, rawValue] = kv;
    const value = rawValue.replace(/^['"]|['"]$/g, '');
    if (key === 'deprecated') {
      (fm as Record<string, unknown>)[key] = value === 'true';
    } else {
      (fm as Record<string, unknown>)[key] = value;
    }
  }
  return { fm, body };
}

function fileToRoute(file: string): string {
  const rel = relative(DOCS_DIR, file).replace(/\\/g, '/').replace(/\.(md|mdx)$/, '');
  if (rel.endsWith('/index')) return rel.slice(0, -'/index'.length) || '/';
  return rel;
}

function categoryOf(file: string): string {
  const rel = relative(DOCS_DIR, file).replace(/\\/g, '/');
  return rel.split('/')[0] ?? 'misc';
}

function stripMdx(body: string): string {
  // Strip MDX imports + JSX components down to plain text. The result
  // is what an LLM agent should see as the "useful" content.
  return body
    .replace(/^import\s+.*?from\s+['"].*?['"];?\s*$/gm, '')
    .replace(/<[A-Z][A-Za-z0-9]*[\s\S]*?\/?>([\s\S]*?<\/[A-Z][A-Za-z0-9]*>)?/g, '')
    .replace(/<[a-z][^>]*>([\s\S]*?<\/[a-z][^>]*>)?/g, '')
    .trim();
}

function bucketLabel(category: string): string {
  switch (category) {
    case 'intro':
      return 'Get started';
    case 'concepts':
      return 'Concepts';
    case 'how-to':
      return 'How-to';
    case 'tutorials':
      return 'Tutorials';
    case 'reference':
      return 'Reference';
    case 'architecture':
      return 'Architecture decisions';
    case 'release-notes':
      return 'Release notes';
    default:
      return category;
  }
}

type Entry = {
  file: string;
  route: string;
  category: string;
  fm: Frontmatter;
  body: string;
};

function buildEntries(): Entry[] {
  const files = walk(DOCS_DIR).sort();
  const entries: Entry[] = [];
  for (const file of files) {
    const raw = readFileSync(file, 'utf-8');
    const { fm, body } = parseFrontmatter(raw);
    if (fm.audience === 'internal') continue;
    const route = fileToRoute(file);
    entries.push({ file, route, category: categoryOf(file), fm, body });
  }
  return entries;
}

function buildIndex(entries: Entry[]): string {
  const lines: string[] = [
    '# Agentic Quant Platform',
    '',
    '> AgenticOps + RL-Ops platform: strategy research, backtests,',
    '> paper, and live trading. Hash-locked spec runtimes, agent',
    '> control plane, Iceberg + pgvector data layer, Kubernetes-',
    '> deployed, Cloudflare-edge-served docs.',
    '',
    `Site URL: ${SITE_URL}`,
    `Total documents: ${entries.length}`,
    `Generated: ${new Date().toISOString().slice(0, 10)}`,
    '',
    '## Adjacent corpora',
    '',
    `- [/llms-full.txt](${SITE_URL}/llms-full.txt) — concatenated full corpus.`,
    `- [/mcp](${SITE_URL}/mcp) — RFC 9728 + 8707-compliant MCP server.`,
    `- [/openapi/aqp.json](${SITE_URL}/openapi/aqp.json) — public API spec.`,
    `- [/openapi/control-plane.json](${SITE_URL}/openapi/control-plane.json) — control-plane spec.`,
    '',
  ];

  const buckets = new Map<string, Entry[]>();
  for (const e of entries) {
    const list = buckets.get(e.category) ?? [];
    list.push(e);
    buckets.set(e.category, list);
  }
  // Stable ordering of categories.
  const ORDER = ['intro', 'tutorials', 'how-to', 'concepts', 'reference', 'architecture', 'release-notes'];
  const sortedCategories = ORDER.concat(
    Array.from(buckets.keys()).filter((c) => !ORDER.includes(c)),
  ).filter((c) => buckets.has(c));

  for (const cat of sortedCategories) {
    lines.push(`## ${bucketLabel(cat)}`);
    lines.push('');
    for (const e of buckets.get(cat)!) {
      const summary = e.fm.summary ?? e.fm.title ?? e.route;
      lines.push(`- [${e.fm.title ?? e.route}](${SITE_URL}/${e.route}): ${summary}`);
    }
    lines.push('');
  }
  return lines.join('\n');
}

function buildFull(entries: Entry[]): string {
  const parts: string[] = [];
  parts.push('# Agentic Quant Platform — full corpus');
  parts.push('');
  parts.push(
    '> Concatenated, MDX-stripped markdown for one-shot LLM ingestion.',
    '> See /llms.txt for the curated index.',
    '',
  );
  for (const e of entries) {
    parts.push(`\n\n<!-- ${SITE_URL}/${e.route} -->`);
    parts.push(`# ${e.fm.title ?? e.route}`);
    if (e.fm.summary) parts.push(`> ${e.fm.summary}`);
    parts.push('');
    parts.push(stripMdx(e.body));
    parts.push('');
  }
  return parts.join('\n');
}

function main(): void {
  mkdirSync(STATIC_DIR, { recursive: true });
  const entries = buildEntries();
  const indexTxt = buildIndex(entries);
  const fullTxt = buildFull(entries);
  writeFileSync(join(STATIC_DIR, 'llms.txt'), indexTxt, 'utf-8');
  writeFileSync(join(STATIC_DIR, 'llms-full.txt'), fullTxt, 'utf-8');
  console.log(
    `[llms-txt] wrote ${entries.length} entries to llms.txt (${(indexTxt.length / 1024).toFixed(1)} KiB)`,
  );
  console.log(`[llms-txt] wrote full corpus to llms-full.txt (${(fullTxt.length / 1024).toFixed(1)} KiB)`);
}

main();
