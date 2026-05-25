// keystatic.config.ts — Git-native, typed CMS for business editors.
//
// The Keystatic UI is mounted alongside the Docusaurus build at
// /keystatic (sidecar Next.js or local dev runner). Editors author
// content through a block UI with typed frontmatter; saving creates
// a branch and opens a PR against the same protected `main` branch
// engineers ship through. There is no parallel CMS database.
//
// Hard rules respected:
//   - aqp_docs/src/lib/frontmatterSchema.ts is the canonical schema
//     for runtime / CI validation; the schemas below MUST match it.
//   - Owner enum is locked to the GitHub Teams that appear in
//     aqp_docs/CODEOWNERS.

import { config, fields, collection } from '@keystatic/core';

const owner = fields.select({
  label: 'Owner',
  description: 'GitHub team responsible for this page. Must match a team in aqp_docs/CODEOWNERS.',
  options: [
    { label: 'Platform team', value: 'platform-team' },
    { label: 'Docs team', value: 'docs-team' },
    { label: 'Data team', value: 'data-team' },
    { label: 'RL team', value: 'rl-team' },
    { label: 'ML team', value: 'ml-team' },
    { label: 'Agentic team', value: 'agentic-team' },
    { label: 'Strategy team', value: 'strategy-team' },
    { label: 'Trading team', value: 'trading-team' },
    { label: 'Identity team', value: 'identity-team' },
    { label: 'Infrastructure team', value: 'infra-team' },
    { label: 'SRE team', value: 'sre-team' },
  ],
  defaultValue: 'docs-team',
});

const audience = fields.select({
  label: 'Audience',
  options: [
    { label: 'Both human + agent', value: 'both' },
    { label: 'Human only', value: 'human' },
    { label: 'Agent only (llms.txt + MCP)', value: 'agent' },
    { label: 'Internal (Cloudflare Access gated)', value: 'internal' },
  ],
  defaultValue: 'both',
});

const lastReviewed = fields.date({
  label: 'Last reviewed',
  description: 'ISO date. The staleness watchdog opens a GitHub Issue when this is >180 days old.',
});

const summary = fields.text({
  label: 'Summary',
  description: 'One-liner consumed by /llms.txt. Keep under 200 characters.',
  multiline: false,
  validation: { length: { min: 1, max: 200 } },
});

const sharedFrontmatter = {
  title: fields.slug({ name: { label: 'Title' } }),
  summary,
  owner,
  audience,
  last_reviewed: lastReviewed,
  version: fields.text({ label: 'Version (optional)', validation: { length: { min: 0, max: 32 } } }),
  deprecated: fields.checkbox({ label: 'Deprecated', defaultValue: false }),
  deprecated_replacement: fields.text({ label: 'Replacement page route (when deprecated)' }),
  keywords: fields.array(fields.text({ label: 'Keyword' }), { label: 'Keywords' }),
};

const conceptCollection = (label: string, path: string) =>
  collection({
    label,
    slugField: 'title',
    path: `docs/concepts/${path}/*`,
    format: { contentField: 'content' },
    schema: {
      ...sharedFrontmatter,
      content: fields.markdoc({
        label: 'Content',
        options: { image: { directory: 'static/img/uploads', publicPath: '/img/uploads/' } },
      }),
    },
  });

export default config({
  storage:
    process.env.NODE_ENV === 'development'
      ? { kind: 'local' }
      : {
          kind: 'github',
          repo: { owner: 'julianwileymac', name: 'agentic_quant_platform' },
        },
  ui: {
    brand: { name: 'AQP Docs' },
    navigation: {
      'Get started': ['intro'],
      Tutorials: ['tutorials'],
      'How-to': ['operations', 'runbooks', 'mlops', 'recipes'],
      Concepts: [
        'concepts-platform',
        'concepts-data',
        'concepts-strategy',
        'concepts-rl',
        'concepts-agentic',
        'concepts-trading',
        'concepts-identity',
        'concepts-infrastructure',
      ],
      'Release notes': ['release-notes'],
    },
  },
  collections: {
    intro: collection({
      label: 'Get started',
      slugField: 'title',
      path: 'docs/intro/*',
      format: { contentField: 'content' },
      schema: {
        ...sharedFrontmatter,
        sidebar_position: fields.integer({ label: 'Sidebar position', validation: { min: 0, max: 999 } }),
        content: fields.markdoc({ label: 'Content' }),
      },
    }),
    tutorials: collection({
      label: 'Tutorials',
      slugField: 'title',
      path: 'docs/tutorials/*',
      format: { contentField: 'content' },
      schema: {
        ...sharedFrontmatter,
        runnable: fields.checkbox({ label: 'Runnable (Pyodide / WebContainer)', defaultValue: false }),
        sidebar_position: fields.integer({ label: 'Sidebar position', validation: { min: 0, max: 999 } }),
        content: fields.markdoc({ label: 'Content' }),
      },
    }),
    operations: collection({
      label: 'How-to: operations',
      slugField: 'title',
      path: 'docs/how-to/operations/*',
      format: { contentField: 'content' },
      schema: {
        ...sharedFrontmatter,
        content: fields.markdoc({ label: 'Content' }),
      },
    }),
    runbooks: collection({
      label: 'How-to: runbooks',
      slugField: 'title',
      path: 'docs/how-to/runbooks/*',
      format: { contentField: 'content' },
      schema: {
        ...sharedFrontmatter,
        content: fields.markdoc({ label: 'Content' }),
      },
    }),
    mlops: collection({
      label: 'How-to: MLOps',
      slugField: 'title',
      path: 'docs/how-to/mlops/*',
      format: { contentField: 'content' },
      schema: {
        ...sharedFrontmatter,
        content: fields.markdoc({ label: 'Content' }),
      },
    }),
    recipes: collection({
      label: 'How-to: recipes',
      slugField: 'title',
      path: 'docs/how-to/recipes/*',
      format: { contentField: 'content' },
      schema: {
        ...sharedFrontmatter,
        content: fields.markdoc({ label: 'Content' }),
      },
    }),
    'concepts-platform': conceptCollection('Concepts: platform', 'platform'),
    'concepts-data': conceptCollection('Concepts: data', 'data'),
    'concepts-strategy': conceptCollection('Concepts: strategy + ML', 'strategy'),
    'concepts-rl': conceptCollection('Concepts: RL', 'rl'),
    'concepts-agentic': conceptCollection('Concepts: agentic', 'agentic'),
    'concepts-trading': conceptCollection('Concepts: trading', 'trading'),
    'concepts-identity': conceptCollection('Concepts: identity + tenancy', 'identity'),
    'concepts-infrastructure': conceptCollection('Concepts: infrastructure', 'infrastructure'),
    'release-notes': collection({
      label: 'Release notes',
      slugField: 'title',
      path: 'docs/release-notes/*',
      format: { contentField: 'content' },
      schema: {
        ...sharedFrontmatter,
        epoch: fields.text({
          label: 'API epoch (Stripe-style)',
          description: 'YYYY-MM-DD. Only set on release notes that move the public API.',
        }),
        breaking: fields.checkbox({ label: 'Breaking change', defaultValue: false }),
        content: fields.markdoc({ label: 'Content' }),
      },
    }),
  },
});
