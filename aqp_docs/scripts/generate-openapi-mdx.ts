// generate-openapi-mdx.ts — emits per-operation MDX pages for both
// OpenAPI specs so the docs-site search + llms.txt corpora index
// every endpoint.
//
// Backed by docusaurus-plugin-openapi-docs in non-CLI mode (so we
// can scope the output paths exactly). Output:
//
//   aqp_docs/docs/reference/api/<tag>/<operationId>.mdx
//   aqp_docs/docs/reference/manage-api/<tag>/<operationId>.mdx
//
// Phase 1 of the migration plan.

import { readFileSync, mkdirSync, writeFileSync, existsSync } from 'node:fs';
import { join, resolve } from 'node:path';

const REPO_ROOT = resolve(__dirname, '..', '..');
const OPENAPI_DIR = join(REPO_ROOT, 'aqp_docs', 'openapi');
const REFERENCE_ROOT = join(REPO_ROOT, 'aqp_docs', 'docs', 'reference');

type OpenAPISpec = {
  info: { title: string; version: string };
  paths: Record<string, Record<string, OpenAPIOperation>>;
};

type OpenAPIOperation = {
  operationId?: string;
  summary?: string;
  description?: string;
  tags?: string[];
};

function slugify(s: string): string {
  return s
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
}

function emitOperationMdx(
  outDir: string,
  spec: OpenAPISpec,
  pathKey: string,
  method: string,
  op: OpenAPIOperation,
  apiSlug: 'api' | 'manage-api',
): void {
  const tag = op.tags?.[0] ?? 'untagged';
  const opId = op.operationId ?? slugify(`${method}-${pathKey}`);
  const tagDir = join(outDir, slugify(tag));
  if (!existsSync(tagDir)) mkdirSync(tagDir, { recursive: true });

  const summary =
    op.summary ?? `${method.toUpperCase()} ${pathKey}`;
  const description = op.description ?? summary;

  const fm = [
    '---',
    `title: '${method.toUpperCase()} ${pathKey}'`,
    `summary: '${summary.replace(/'/g, '')}'`,
    `owner: platform-team`,
    `last_reviewed: ${new Date().toISOString().slice(0, 10)}`,
    `audience: both`,
    `sidebar_label: '${pathKey}'`,
    '---',
    '',
    `# ${summary}`,
    '',
    description,
    '',
    `> **Method:** \`${method.toUpperCase()}\``,
    `> **Path:** \`${pathKey}\``,
    `> **Tag:** \`${tag}\``,
    `> **OperationId:** \`${opId}\``,
    '',
    'See the [interactive playground](../index.mdx) for parameter',
    'forms, response schemas, and credential persistence.',
    '',
    '## Source spec',
    '',
    `This page is generated from \`aqp_docs/openapi/${apiSlug === 'manage-api' ? 'control-plane' : 'aqp'}.json\` by`,
    '[`aqp_docs/scripts/generate-openapi-mdx.ts`](https://github.com/julianwileymac/agentic_quant_platform/blob/main/aqp_docs/scripts/generate-openapi-mdx.ts).',
    'Refresh by re-running `pnpm --filter aqp_docs generate-openapi-mdx`.',
    '',
  ].join('\n');

  writeFileSync(join(tagDir, `${slugify(opId)}.mdx`), fm, 'utf-8');
}

function run(specPath: string, outDir: string, slug: 'api' | 'manage-api'): void {
  if (!existsSync(specPath)) {
    console.warn(`[openapi-mdx] missing spec ${specPath}; skipping`);
    return;
  }
  const spec = JSON.parse(readFileSync(specPath, 'utf-8')) as OpenAPISpec;
  if (!spec.paths) {
    console.warn(`[openapi-mdx] spec has no paths; skipping ${slug}`);
    return;
  }
  mkdirSync(outDir, { recursive: true });
  let n = 0;
  for (const [pathKey, methods] of Object.entries(spec.paths)) {
    for (const [method, op] of Object.entries(methods)) {
      if (!['get', 'post', 'put', 'patch', 'delete', 'options', 'head'].includes(method)) continue;
      emitOperationMdx(outDir, spec, pathKey, method, op, slug);
      n += 1;
    }
  }
  console.log(`[openapi-mdx] ${slug}: emitted ${n} operation MDX page(s) under ${outDir}`);
}

run(join(OPENAPI_DIR, 'aqp.json'), join(REFERENCE_ROOT, 'api'), 'api');
run(join(OPENAPI_DIR, 'control-plane.json'), join(REFERENCE_ROOT, 'manage-api'), 'manage-api');
